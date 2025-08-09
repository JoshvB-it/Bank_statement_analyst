# streamlit_app.py
# FNB Statement Analyzer — row-stitching parser + running-balance deltas
# Requires: streamlit==1.30.0, PyMuPDF==1.25.5, pandas==2.2.2

import os, re, tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
PARSER_VERSION = "2025-08-09-r6"

# ---- Auth (supports ?pw=...) ----
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

# ---- Helpers / patterns ----
MONTHS_3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()
NUM_CORE = r"\d{1,3}(?:,\d{3})*\.\d{2}"   # force cents to dodge card refs like 431835*1425
NUM_TOKEN = re.compile(rf"^{NUM_CORE}$")
CRDR = re.compile(r"^[Cc][Rr]$|^[Dd][Rr]$")
DATE_ROW = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\b", re.I)

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

# ---- Word/row utilities ----
def build_rows(doc: fitz.Document):
    """Return visual rows as token lists (y-rounded lines, in page order)."""
    rows = []
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
            rows.append({
                "text": " ".join(g["text"].tolist()).strip(),
                "tokens": g["text"].tolist(),
                "x": g["x0"].tolist()
            })
    return rows

def parse_transactions_rows(doc: fitz.Document, year_hint: Optional[int], opening: Optional[float]):
    """Stitch wrapped rows: from each date row, scan forward until amount & balance appear."""
    rows = build_rows(doc)
    tx = []
    prev_running = opening
    i, n = 0, len(rows)

    while i < n:
        r = rows[i]
        if not DATE_ROW.match(r["text"]):
            i += 1
            continue

        # gather description tokens until we encounter the first numeric-with-cents
        desc_tokens = r["tokens"][:]   # start with tokens on the date row
        amount_tok = None
        runbal_tok = None

        j = i
        while True:
            # find first numeric in current row if needed
            if amount_tok is None:
                for t in rows[j]["tokens"]:
                    if NUM_TOKEN.match(t):
                        amount_tok = t
                        break
            else:
                # keep track of the last numeric before the next date -> running balance
                for t in rows[j]["tokens"][::-1]:
                    if NUM_TOKEN.match(t):
                        runbal_tok = t
                        break

            # extend desc with non-numeric / non-CRDR tokens
            if j != i:  # include tokens from intermediate lines
                desc_tokens += [t for t in rows[j]["tokens"] if not (NUM_TOKEN.match(t) or CRDR.match(t))]

            # stop when next visual row starts with a date or we’ve scanned past end
            if (j + 1 >= n) or DATE_ROW.match(rows[j + 1]["text"]):
                break
            j += 1

        # Fallbacks: if amount/balance still not seen, try date row tokens
        if amount_tok is None:
            for t in r["tokens"]:
                if NUM_TOKEN.match(t):
                    amount_tok = t; break
        if runbal_tok is None:
            for t in r["tokens"][::-1]:
                if NUM_TOKEN.match(t):
                    runbal_tok = t; break

        # Convert tokens to values
        amount_val = float(amount_tok.replace(",", "")) if amount_tok else 0.0
        runbal_val = float(runbal_tok.replace(",", "")) if runbal_tok else None

        # Prefer running-balance delta for the true signed amount
        amt = amount_val
        if (runbal_val is not None) and (prev_running is not None):
            amt = round(runbal_val - prev_running, 2)
            prev_running = runbal_val

        # Build clean description: tokens from after the date up to before the first numeric we encountered
        # (remove numeric and CR/DR tokens that we appended from wrapped lines)
        clean_desc = []
        started = False
        for t in desc_tokens:
            if not started:
                started = True  # first token is day, skip only for spacing; we keep rest
                continue
            if NUM_TOKEN.match(t) or CRDR.match(t):
                continue
            clean_desc.append(t)
        desc = " ".join(clean_desc).strip()

        # Parse date from the first two tokens in the original row text
        m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\b", r["text"])
        mon = m.group(2).title(); day = int(m.group(1))
        year = year_hint or datetime.now().year
        dt = datetime.strptime(f"{day:02d} {mon} {year}", "%d %b %Y")

        tx.append((dt, desc, amt))
        i = j + 1  # jump to the next date block

    return tx

# ---- Classification ----
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

def parse_file(path: str) -> Dict[str, Any]:
    doc = fitz.open(path)
    try:
        full_text = "\n".join(pg.get_text("text") for pg in doc)
        opening, closing = parse_balances_text(full_text)
        year = try_parse_statement_year(full_text) or datetime.now().year
        txns = parse_transactions_rows(doc, year, opening)
        return {
            "year": year,
            "transactions": txns,
            "opening": opening,
            "closing": closing,
            "leftovers": [],  # row-stitching avoids most leftovers
        }
    finally:
        doc.close()

# ---- App ----
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

    balance_rows, all_tx = [], []

    for file in uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        parsed = parse_file(tmp_path)
        txns = parsed["transactions"]
        opening, closing = parsed["opening"], parsed["closing"]

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

        with st.expander(f"🔎 Diagnostics — {Path(file.name).stem}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Detected year:**", parsed["year"])
                st.write("**Opening / Closing (raw parsed):**", opening, closing)
                st.write("**Transactions parsed:**", len(txns))
            with c2:
                st.write("Row-stitching parser enabled")

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
            file_name="transactions.csv", mime="text/csv",
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
        st.download_button(
            "⬇️ Download reconciliation CSV",
            data=df_bal.to_csv(index=False).encode("utf-8"),
            file_name="reconciliation.csv", mime="text/csv",
            use_container_width=True
        )

if __name__ == "__main__":
    main()