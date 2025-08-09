# streamlit_app.py
# FNB Statement Analyzer — row-stitching parser + attached Cr/Dr + continuity check
# Requires: streamlit==1.30.0, PyMuPDF==1.25.5, pandas==2.2.2

import os, re, tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
PARSER_VERSION = "2025-08-09-r7"

# --- Auth (supports ?pw=...) ---
try:
    SECRET_PW = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
except Exception:
    SECRET_PW = None
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD") or SECRET_PW or "changeme"

st.title("📑 FNB Bank Statement Analyzer")
st.caption(f"Parser version: {PARSER_VERSION}")

try:
    qparams = st.experimental_get_query_params()
except Exception:
    qparams = {}
qpw = (qparams.get("pw", [None])[0] if isinstance(qparams.get("pw"), list) else qparams.get("pw"))
if "pw_ok" not in st.session_state:
    st.session_state.pw_ok = (qpw == DEFAULT_PASSWORD)
if not st.session_state.pw_ok:
    st.info("Enter the password to proceed. (Tip: append `?pw=...` to the URL)")
    pwd = st.text_input("Password", value=qpw or "", type="password")
    if st.button("Unlock"):
        st.session_state.pw_ok = (pwd == DEFAULT_PASSWORD)
        if not st.session_state.pw_ok:
            st.error("Incorrect password")
    st.stop()

# -------- Patterns & helpers --------
MONTHS_3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()
DATE_ROW = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\b", re.I)
NUM_ATT = re.compile(r"^(\d{1,3}(?:,\d{3})*\.\d{2})([Cc][Rr]|[Dd][Rr])?$")  # e.g. 10,878.94  | 10,878.94Cr

def try_parse_statement_year(text: str) -> Optional[int]:
    m = re.search(r"Statement\s*Date\s*:\s*\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b(?:Period|From)\b.*?\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4}).*?\bto\b.*?(\d{4})", text, re.I|re.S)
    if m: return int(m.group(2))
    m = re.search(r"\bas\s+at\s+\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else None

def parse_balances_text(text: str) -> Tuple[Optional[float], Optional[float]]:
    num = r"\d{1,3}(?:,\d{3})*\.\d{2}"
    rx_open = re.compile(rf"Opening\s*Balance.*?({num})\s*([Cc][Rr]|[Dd][Rr])?", re.S)
    rx_close = re.compile(rf"Closing\s*Balance.*?({num})\s*([Cc][Rr]|[Dd][Rr])?", re.S)
    def one(rx):
        m = rx.search(text)
        if not m: return None
        v = float(m.group(1).replace(",", ""))
        tag = (m.group(2) or "CR").upper()
        return -abs(v) if tag == "DR" else abs(v)
    return one(rx_open), one(rx_close)

# ---- Type Classification (Income / Expense / Transfer) ----
TRANSFER_KEYWORDS = [
    "transfer","inter-account","inter account","internal tf","bankapp transfer",
    "bank app transfer","e-wallet","ewallet","eft","rtgs","instant payment",
    "pay and clear","recon","faster payment","own account","to savings","from savings",
    "global payment"
]
def classify_type(description: str, amount: float) -> str:
    d = description.lower()
    is_transfer = any(k in d for k in TRANSFER_KEYWORDS)
    if amount > 0:
        return "Transfer In" if is_transfer else "Income"
    elif amount < 0:
        return "Transfer Out" if is_transfer else "Expense"
    else:
        return "Zero / Reversal"

# -------- Core: row-aware parser (handles wrapped lines + attached Cr/Dr) --------
def parse_transactions_words(doc: fitz.Document, year_hint: Optional[int], opening: Optional[float]):
    tx = []
    prev_running = opening

    for page in doc:
        words = page.get_text("words")
        if not words:
            continue
        df = pd.DataFrame(words, columns=["x0","y0","x1","y1","text","block","line","word"])
        if df.empty:
            continue
        df["y_round"] = df["y0"].round(1)

        for y, g in df.groupby("y_round"):
            g = g.sort_values("x0")
            row_text = " ".join(g["text"].tolist())
            if not DATE_ROW.match(row_text):
                continue

            # numeric candidates (amount/balance/possibly accrued), allowing attached Cr/Dr
            cands = [(t, x) for t, x in zip(g["text"], g["x0"]) if NUM_ATT.match(t)]
            if not cands:
                continue
            cands.sort(key=lambda r: r[1])

            # Amount = first numeric
            m1 = NUM_ATT.match(cands[0][0])
            amt_val = float(m1.group(1).replace(",", ""))
            amt_tag = (m1.group(2) or "").upper()
            amount_raw = -amt_val if amt_tag == "DR" else amt_val

            # Running balance = second-last when we have ≥3 numerics (to skip Accrued); else last
            if len(cands) >= 3:
                cand_bal = cands[-2][0]
            else:
                cand_bal = cands[-1][0]
            m2 = NUM_ATT.match(cand_bal)
            rb_val = float(m2.group(1).replace(",", ""))
            rb_tag = (m2.group(2) or "").upper()
            runbal = -rb_val if rb_tag == "DR" else rb_val

            # True signed amount from running-balance delta
            amt = amount_raw
            if (runbal is not None) and (prev_running is not None):
                amt = round(runbal - prev_running, 2)
                prev_running = runbal

            # Date + description (tokens up to first numeric)
            tokens = g["text"].tolist()
            # date pieces
            day = None; mon = None
            for i,t in enumerate(tokens):
                if re.match(r"^\d{1,2}$", t) and i+1 < len(tokens) and re.match(r"^[A-Za-z]{3}$", tokens[i+1]):
                    day = int(t); mon = tokens[i+1].title(); break
            if day is None:
                continue
            year = year_hint or datetime.now().year
            dt = datetime.strptime(f"{day:02d} {mon} {year}", "%d %b %Y")

            # description before first numeric
            first_idx = next(i for i,t in enumerate(tokens) if NUM_ATT.match(t))
            desc = " ".join(tokens[1:first_idx]).strip()

            tx.append((dt, desc, amt))
    return tx

def parse_file(path: str) -> Dict[str, Any]:
    doc = fitz.open(path)
    try:
        full_text = "\n".join(pg.get_text("text") for pg in doc)
        opening, closing = parse_balances_text(full_text)
        year = try_parse_statement_year(full_text) or datetime.now().year
        txns = parse_transactions_words(doc, year, opening)
        return {
            "year": year,
            "transactions": txns,
            "opening": opening,
            "closing": closing,
        }
    finally:
        doc.close()

# ---------------- App ----------------
def main():
    st.sidebar.subheader("Options")
    tol = st.sidebar.number_input("Reconciliation tolerance (ZAR)", value=0.01, step=0.01, min_value=0.00, format="%.2f")

    uploaded = st.file_uploader(
        "Upload FNB bank statement PDFs",
        type=["pdf"], accept_multiple_files=True,
        help="You can upload multiple months at once."
    )
    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_rows = []
    all_tx = []
    per_file_dates = {}

    for file in uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        parsed = parse_file(tmp_path)
        txns: List[Tuple[datetime, str, float]] = parsed["transactions"]
        opening = parsed["opening"]
        closing = parsed["closing"]

        # Detailed rows + tx dates
        if txns:
            first_dt = min(dt for dt,_,_ in txns if dt is not None)
            per_file_dates[Path(file.name).stem] = first_dt

        for dt, desc, amt in txns:
            all_tx.append({
                "Statement": Path(file.name).stem,
                "Date": dt,
                "Description": desc,
                "Amount (ZAR)": round(amt, 2),
                "Type": classify_type(desc, amt),
            })

        net = round(sum(a for _, _, a in txns), 2)
        expected = (round(opening, 2) + net) if opening is not None else None
        diff = (round(closing, 2) - expected) if (closing is not None and expected is not None) else None

        balance_rows.append({
            "Statement": Path(file.name).stem,
            "Opening (ZAR)": None if opening is None else round(opening, 2),
            "Net (ZAR)": net,
            "Expected (ZAR)": None if expected is None else round(expected, 2),
            "Closing (ZAR)": None if closing is None else round(closing, 2),
            "Difference (ZAR)": None if diff is None else round(diff, 2),
            "Parsed Tx Count": len(txns),
        })

    # Detailed transactions
    st.subheader("Detailed Transactions")
    if all_tx:
        df_tx = pd.DataFrame(all_tx).sort_values(["Statement", "Date"]).reset_index(drop=True)
        st.dataframe(df_tx, use_container_width=True, height=420)

        st.markdown("**Summary by Type**")
        g = df_tx.groupby("Type")["Amount (ZAR)"].sum().reset_index().sort_values("Amount (ZAR)", ascending=False)
        st.dataframe(g, use_container_width=True)

        st.download_button(
            "⬇️ Download transactions CSV",
            data=df_tx.to_csv(index=False).encode("utf-8"),
            file_name="transactions.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("No transactions parsed yet.")

    # Balance reconciliation
    st.subheader("Balance Reconciliation Summary")
    df_bal = pd.DataFrame(balance_rows)
    if not df_bal.empty:
        st.dataframe(df_bal, use_container_width=True)
        any_diff = df_bal["Difference (ZAR)"].notna() & (df_bal["Difference (ZAR)"].abs() > tol)
        if any_diff.any():
            st.warning("Some statements have differences greater than the tolerance.")
        else:
            st.success("All statements reconcile (Expected Closing ≈ Actual Closing within tolerance).")

        # --- Continuity check: Closing[i] ≈ Opening[i+1] ---
        if per_file_dates:
            order = sorted(per_file_dates.items(), key=lambda kv: kv[1])
            ordered_names = [name for name,_ in order]
            df = df_bal.set_index("Statement").loc[ordered_names].reset_index()
            cont_rows = []
            for i in range(len(df)-1):
                a = df.loc[i, "Statement"]; b = df.loc[i+1, "Statement"]
                clo = df.loc[i, "Closing (ZAR)"]; opn = df.loc[i+1, "Opening (ZAR)"]
                delta = None if (pd.isna(clo) or pd.isna(opn)) else round(opn - clo, 2)
                ok = (delta is not None) and (abs(delta) <= tol)
                cont_rows.append({"From": a, "To (next)": b, "Prev Closing (ZAR)": clo, "Next Opening (ZAR)": opn, "Δ (should be 0)": delta, "OK": "✅" if ok else "❌"})
            st.markdown("**Statement Continuity Check**")
            st.dataframe(pd.DataFrame(cont_rows), use_container_width=True)

        st.download_button(
            "⬇️ Download reconciliation CSV",
            data=df_bal.to_csv(index=False).encode("utf-8"),
            file_name="reconciliation.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("No balances to show yet.")

if __name__ == "__main__":
    main()