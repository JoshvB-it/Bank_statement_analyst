# FNB Statement Analyzer — word/row parser + running-balance deltas
# Requires: streamlit==1.30.0, PyMuPDF==1.25.5, pandas==2.2.2

import os, re, tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
PARSER_VERSION = "2025-08-09-r5"

# Password (env/Secrets) — default for local
try:
    SECRET_PW = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
except Exception:
    SECRET_PW = None
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD") or SECRET_PW or "changeme"

st.title("📑 FNB Bank Statement Analyzer")
st.caption(f"Parser version: {PARSER_VERSION}")

# --- Simple auth (supports ?pw=...) ---
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

# ---------------- Helpers ----------------
MONTHS_3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()
NUM_CORE = r"\d{1,3}(?:,\d{3})*\.\d{2}"  # force cents to avoid grabbing card refs etc.
NUM_TOKEN_ATT = re.compile(rf"^({NUM_CORE})([Cc][Rr]|[Dd][Rr])?$")  # e.g. 10,878.94  | 10,878.94Cr

HEADER_NOISE = [re.compile(p, re.I) for p in [
    r"^page\s+\d+\s+of\s+\d+$",
    r"^fnb\b.*",
    r"^first national bank\b.*",
    r"^branch\b.*",
    r"^account\b.*",
    r"^statement\b.*",
    r"^transactions in rand.*$",
    r"^date\s+description\s+amount\s+balance.*$",
    r"^delivery method.*$",
    r"^bank charges.*$",
    r"^interest rate.*$",
    r"^service fees.*$",
    r"^total vat.*$",
    r"^inclusive of vat.*$",
    r"^closing balance.*$",
    r"^opening balance.*$",
]]

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

def classify_type(description: str, amount: float) -> str:
    TRANSFER_KEYWORDS = [
        "transfer","inter-account","inter account","internal tf","bankapp transfer",
        "bank app transfer","e-wallet","ewallet","eft","rtgs","instant payment",
        "pay and clear","recon","faster payment","own account","to savings","from savings",
        "global payment"
    ]
    d = description.lower()
    is_transfer = any(k in d for k in TRANSFER_KEYWORDS)
    if amount > 0:
        return "Transfer In" if is_transfer else "Income"
    elif amount < 0:
        return "Transfer Out" if is_transfer else "Expense"
    else:
        return "Zero / Reversal"

# ---------------- Core: word/row parser ----------------
def iter_rows_words(doc: fitz.Document):
    """Yield row dicts from PyMuPDF word coordinates (one dict per printed row)."""
    for pageno, page in enumerate(doc):
        # exclude obvious header/footer noise by line prefix
        words = page.get_text("words")  # (x0,y0,x1,y1,text, block, line, word)
        if not words:
            continue
        df = pd.DataFrame(words, columns=["x0","y0","x1","y1","text","block","line","word"])
        if df.empty:
            continue
        # Drop lines that are clearly headings
        df["keep"] = True
        mask_drop = pd.Series(False, index=df.index)
        for rx in HEADER_NOISE:
            mask_drop |= df["text"].str.match(rx)
        df = df.loc[~mask_drop].copy()

        df["y_round"] = df["y0"].round(1)
        for y, g in df.groupby("y_round"):
            g = g.sort_values("x0")
            tokens = g["text"].tolist()
            row_text = " ".join(tokens).strip()
            yield {"page": pageno, "y": float(y), "tokens": tokens, "x": g["x0"].tolist(), "text": row_text}

def parse_transactions_words(doc: fitz.Document, year_hint: Optional[int], opening: Optional[float]):
    """Return list[(date, desc, signed_amount)] using row-aware parsing."""
    tx = []
    prev_running = opening
    DATE_ROW = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\b")

    for row in iter_rows_words(doc):
        text = row["text"]
        if not DATE_ROW.match(text):
            continue

        # Find numeric-with-cents tokens in order (accept attached Cr/Dr)
        nums = []
        for t, x in zip(row["tokens"], row["x"]):
            m = NUM_TOKEN_ATT.match(t)
            if m:
                val = float(m.group(1).replace(",", ""))
                tag = (m.group(2) or "").upper()
                nums.append((x, val, tag))
        if not nums:
            continue

        nums.sort(key=lambda r: r[0])
        # amount = first numeric; running balance = last numeric (if 2+)
        a_val, a_tag = nums[0][1], nums[0][2]
        amount_raw = -a_val if a_tag == "DR" else a_val
        runbal = None
        if len(nums) > 1:
            rb_val, rb_tag = nums[-1][1], nums[-1][2]
            runbal = -rb_val if rb_tag == "DR" else rb_val

        # Derive true signed amount from running-balance delta (preferred)
        amount = amount_raw
        if (runbal is not None) and (prev_running is not None):
            amount = round(runbal - prev_running, 2)
            prev_running = runbal

        # Build date + description (strip trailing amount/balance tokens from desc)
        mdate = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\b(.*)$", text)
        if not mdate:
            continue
        d, mon, rest = mdate.groups()
        year = year_hint or datetime.now().year
        dt = datetime.strptime(f"{int(d):02d} {mon.title()} {year}", "%d %b %Y")

        # remove the trailing numeric tokens from desc
        toks = row["tokens"]
        # find index of the first numeric token -> cut desc before it
        first_num_idx = None
        for idx, t in enumerate(toks):
            if NUM_TOKEN_ATT.match(t):
                first_num_idx = idx
                break
        desc_tokens = toks[1:first_num_idx] if first_num_idx is not None else toks[1:]
        desc = " ".join(desc_tokens).strip()

        tx.append((dt, desc, amount))
    return tx

def parse_file(path: str) -> Dict[str, Any]:
    doc = fitz.open(path)
    try:
        text = "\n".join(pg.get_text("text") for pg in doc)
        opening, closing = parse_balances_text(text)
        year = try_parse_statement_year(text) or datetime.now().year
        txns = parse_transactions_words(doc, year, opening)
        leftovers: List[str] = []  # row parser is strict; we don’t need leftovers for now
        return {
            "year": year,
            "transactions": txns,
            "opening": opening,
            "closing": closing,
            "leftovers": leftovers,
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

    balance_rows, all_tx = [], []

    for file in uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        parsed = parse_file(tmp_path)
        txns = parsed["transactions"]
        opening, closing = parsed["opening"], parsed["closing"]

        # rows for detail + classification
        for dt, desc, amt in txns:
            all_tx.append({
                "Statement": Path(file.name).stem,
                "Date": dt, "Description": desc,
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