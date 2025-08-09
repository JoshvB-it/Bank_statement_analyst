# streamlit_app.py
# FNB Bank Statement Analyzer — mobile-friendly auth + robust parser
# Requires: streamlit==1.30.0, PyMuPDF==1.25.5, pandas==2.2.2, altair==5.2.0

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st

# ---------------- UI / Meta ----------------
st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
PARSER_VERSION = "2025-08-09-r1"

# Password can come from Streamlit Secrets or environment; falls back to 'changeme' for local dev.
try:
    SECRET_PW = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
except Exception:
    SECRET_PW = None
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD") or SECRET_PW or "changeme"

st.title("📑 FNB Bank Statement Analyzer")
st.caption(f"Parser version: {PARSER_VERSION}")

# ---------------- Mobile-friendly Auth ----------------
try:
    qparams = st.experimental_get_query_params()  # works on Streamlit Cloud and local
except Exception:
    qparams = {}
qpw = None
if isinstance(qparams, dict) and "pw" in qparams:
    val = qparams["pw"]
    qpw = val[0] if isinstance(val, list) else val

if "pw_ok" not in st.session_state:
    st.session_state.pw_ok = (qpw == DEFAULT_PASSWORD)

if not st.session_state.pw_ok:
    st.info("Enter the password to proceed. (Tip: you can append `?pw=...` to the URL)")
    pwd = st.text_input("Password", value=qpw or "", type="password")
    if st.button("Unlock"):
        st.session_state.pw_ok = (pwd == DEFAULT_PASSWORD)
        if not st.session_state.pw_ok:
            st.error("Incorrect password")
    st.stop()

# ---------------- Helpers ----------------
MONTHS_3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()

HEADER_NOISE_PATTERNS = [
    r"^page\s+\d+\s+of\s+\d+$",
    r"^fnb\b.*",
    r"^first national bank\b.*",
    r"^branch\b.*",
    r"^account\b.*",
    r"^statement\b.*",
    r"^customer\b.*",
    r"^contact\b.*",
    r"^vat\b.*",
    r"^registered\b.*",
    r"^www\.",
    r"^tel\b.*",
]
HEADER_NOISE_RE = [re.compile(pat, re.IGNORECASE) for pat in HEADER_NOISE_PATTERNS]

def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for rx in HEADER_NOISE_RE:
        if rx.match(s):
            return True
    return False

def clean_amount(raw: str) -> float:
    """
    Accepts many shapes like:
      '1,234.56', 'R 1,234.56', '(1,234.56)', '-1,234.56',
      '1,234.56 CR/DR', 'CR 1,234.56', '1,234.56CR', '1,234.56 DR 12,345.67'
    Returns signed float (credits positive, debits negative by default).
    """
    s = raw.strip()
    # Detect CR/DR anywhere in token
    cr = bool(re.search(r"\bCR\b", s, re.IGNORECASE))
    dr = bool(re.search(r"\bDR\b", s, re.IGNORECASE))

    # Remove explicit CR/DR marks and currency symbol
    s = re.sub(r"\b(CR|DR)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[Rr]\s*", "", s).strip()

    # If an amount and running balance appear on same line, keep the FIRST numeric token as the amount
    nums = re.findall(r"\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?", s)
    if not nums:
        raise ValueError(f"Cannot find numeric amount in: {raw!r}")
    s = nums[0]

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]

    s = s.replace(",", "")
    val = float(s)

    if cr:
        val = abs(val)
    elif dr:
        val = -abs(val)
    elif neg:
        val = -abs(val)

    return val

def try_parse_statement_year(text: str) -> Optional[int]:
    m = re.search(r"Statement\s*Date\s*:\s*\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:Period|From)\b.*?\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4}).*?\bto\b.*?(\d{4})", text, re.IGNORECASE | re.S)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return y2
    m = re.search(r"\bas\s+at\s+\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None

def tokenize_lines(doc: fitz.Document) -> List[str]:
    lines: List[str] = []
    for page in doc:
        # get_text("text") preserves reading order better than blocks for FNB
        for ln in page.get_text("text").splitlines():
            s = ln.strip()
            if is_noise(s):
                continue
            lines.append(s)
    # collapse multiple blanks
    out = []
    blank = False
    for s in lines:
        if not s:
            if not blank:
                out.append(s)
            blank = True
        else:
            out.append(s)
            blank = False
    return out

# ---------------- Parsers ----------------
# Dates like: "3 Jan", "03 Jan", "3 JAN". We'll attach the detected year later.
DATE_START_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3})\b(.*)$", re.IGNORECASE)

# Amount line (captures first numeric as amount; permits trailing running balance)
AMOUNT_LINE_RE = re.compile(
    r"""
    ^
    (?:.*?\b(?:CR|DR)\b\s*)?                              # optional leading CR/DR
    (?:.*?\b[Rr]\s*)?                                     # optional 'R' before amount
    (\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)              # CAPTURE: amount (first numeric token)
    (?:\s*\b(?:CR|DR)\b)?                                 # optional CR/DR after amount
    (?:\s+(?:\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)(?:\s*\b(?:CR|DR)\b)?\s*)?  # optional trailing running balance
    $
    """,
    re.VERBOSE,
)

def parse_transactions_from_lines(lines: List[str], year: int) -> Tuple[List[Tuple[datetime, str, float]], List[str]]:
    txns: List[Tuple[datetime, str, float]] = []
    leftovers: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        m_date = DATE_START_RE.match(line)
        if not m_date:
            i += 1
            continue

        day, mon, rest = m_date.groups()
        mon = mon.strip()[:3].lower()
        if mon not in MONTHS_3:
            i += 1
            continue

        desc_parts = []
        if rest:
            desc_parts.append(rest.strip())

        # Scan forward until we hit amount line or next date
        j = i + 1
        amount_line = None
        while j < n:
            cand = lines[j].strip()
            if DATE_START_RE.match(cand):
                break
            if AMOUNT_LINE_RE.match(cand):
                amount_line = cand
                break
            if cand:
                desc_parts.append(cand)
            j += 1

        if amount_line:
            desc = " ".join(" ".join(desc_parts).split())
            m_amt = AMOUNT_LINE_RE.match(amount_line)
            raw_amt = m_amt.group(1)
            # If CR/DR present anywhere on the line, retain it for sign logic
            crdr = ""
            if re.search(r"\bCR\b", amount_line, re.IGNORECASE):
                crdr = " CR"
            elif re.search(r"\bDR\b", amount_line, re.IGNORECASE):
                crdr = " DR"
            amt = clean_amount(f"{raw_amt}{crdr}")
            try:
                dt = datetime.strptime(f"{int(day):02d} {mon.title()} {year}", "%d %b %Y")
                txns.append((dt, desc, amt))
            except Exception:
                leftovers.append(f"[DATEERR] {day} {mon} :: {desc} :: {amount_line}")
            i = j + 1
        else:
            snippet = " | ".join([line] + lines[i+1:j])
            leftovers.append(f"[UNTERMINATED] {snippet[:240]}")
            i = j
    return txns, leftovers

BALANCE_RE = re.compile(
    r"""
    \b(Opening|Closing)\s*balance\b
    (?:\s*(?:as\s*at)?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}))?
    [\s:]*[Rr]?\s*
    (\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)
    (?:\s*(CR|DR))?
    """,
    re.IGNORECASE | re.VERBOSE,
)
ALT_CLOSING_RE = re.compile(
    r"""
    \b(?:Available|Current)\s*balance\b
    (?:\s*(?:as\s*at)?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}))?
    [\s:]*[Rr]?\s*
    (\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)
    (?:\s*(CR|DR))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

def parse_balances_text(text: str) -> Tuple[Optional[float], Optional[float]]:
    opening = None
    closing = None
    for m in BALANCE_RE.finditer(text):
        label = m.group(1).lower()
        num = m.group(2)
        crdr = m.group(3) or ""
        val = clean_amount(f"{num} {crdr}".strip())
        if label == "opening":
            opening = val
        else:
            closing = val
    if closing is None:
        m = ALT_CLOSING_RE.search(text)
        if m:
            num = m.group(1)
            crdr = m.group(2) or ""
            closing = clean_amount(f"{num} {crdr}".strip())
    return opening, closing

# ---- Simple Type Classification (Income / Expense / Transfer) ----
TRANSFER_KEYWORDS = [
    "transfer", "inter-account", "inter account", "internal tf",
    "bankapp transfer", "bank app transfer", "e-wallet", "ewallet",
    "eft", "rtgs", "instant payment", "pay and clear", "recon",
    "faster payment", "own account", "to savings", "from savings",
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
        full_text = "\n".join(page.get_text("text") for page in doc)
        year = try_parse_statement_year(full_text) or datetime.now().year

        lines = tokenize_lines(doc)
        txns, leftovers = parse_transactions_from_lines(lines, year)
        opening, closing = parse_balances_text(full_text)

        return {
            "year": year,
            "transactions": txns,
            "opening": opening,
            "closing": closing,
            "leftovers": leftovers,
            "lines": lines,
        }
    finally:
        doc.close()

# ---------------- App ----------------
def main():
    st.sidebar.subheader("Options")
    show_leftovers = st.sidebar.checkbox("Show unparsed candidate lines", value=False)
    tol = st.sidebar.number_input("Reconciliation tolerance (ZAR)", value=0.01, step=0.01, min_value=0.00, format="%.2f")

    uploaded = st.file_uploader(
        "Upload FNB bank statement PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        help="You can upload multiple months at once."
    )
    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_rows = []
    all_tx = []

    for file in uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        parsed = parse_file(tmp_path)
        txns: List[Tuple[datetime, str, float]] = parsed["transactions"]
        opening = parsed["opening"]
        closing = parsed["closing"]

        # Build detailed rows with classification
        for dt, desc, amt in txns:
            all_tx.append({
                "Statement": Path(file.name).stem,
                "Date": dt,
                "Description": desc,
                "Amount (ZAR)": round(amt, 2),
                "Type": classify_type(desc, amt),
            })

        net = sum(a for _, _, a in txns)
        expected = (opening + net) if opening is not None else None
        diff = (closing - expected) if (closing is not None and expected is not None) else None

        balance_rows.append({
            "Statement": Path(file.name).stem,
            "Opening Balance (ZAR)": None if opening is None else round(opening, 2),
            "Net Movement (ZAR)": round(net, 2),
            "Expected Closing (ZAR)": None if expected is None else round(expected, 2),
            "Actual Closing (ZAR)": None if closing is None else round(closing, 2),
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
                if show_leftovers and parsed["leftovers"]:
                    st.write("**Unparsed candidate lines** (investigate these):")
                    st.dataframe(pd.DataFrame({"snippet": parsed["leftovers"]}))
                else:
                    st.write("Leftovers hidden. Enable in sidebar to inspect.")

    # Detailed transactions
    st.subheader("Detailed Transactions")
    if all_tx:
        df_tx = pd.DataFrame(all_tx).sort_values(["Statement", "Date"]).reset_index(drop=True)
        # Ensure income positive, expenses negative by sign of amount (already ensured via parsing)
        st.dataframe(df_tx, use_container_width=True, height=420)

        # Quick type summary
        st.markdown("**Summary by Type**")
        g = df_tx.groupby("Type")["Amount (ZAR)"].sum().reset_index().sort_values("Amount (ZAR)", ascending=False)
        st.dataframe(g, use_container_width=True)

        # Download
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
            st.warning("Some statements have differences greater than the tolerance. Expand Diagnostics above and check **Unparsed candidate lines**.")
        else:
            st.success("All statements reconcile (Expected Closing ≈ Actual Closing within tolerance).")
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