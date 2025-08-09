# streamlit_app.py
# FNB Bank Statement Analyzer — row-accurate parser using running-balance deltas
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
PARSER_VERSION = "2025-08-09-r4"

# Password from Secrets / env, fallback for local
try:
    SECRET_PW = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
except Exception:
    SECRET_PW = None
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD") or SECRET_PW or "changeme"

st.title("📑 FNB Bank Statement Analyzer")
st.caption(f"Parser version: {PARSER_VERSION}")

# ---------------- Mobile-friendly Auth ----------------
try:
    qparams = st.experimental_get_query_params()
except Exception:
    qparams = {}
qpw = None
if isinstance(qparams, dict) and "pw" in qparams:
    val = qparams["pw"]
    qpw = val[0] if isinstance(val, list) else val

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

# ---------------- Patterns & helpers ----------------
MONTHS_3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()
NUM = r"\d{1,3}(?:,\d{3})*\.\d{2}"  # enforce cents to avoid grabbing "431835*1425" etc.

DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3})\b(.*)$", re.I)
NUM_WITH_TAG = re.compile(rf"^\s*(?:[Rr]\s*)?({NUM})\s*([Cc][Rr]|[Dd][Rr])?\s*$")  # matches "10,878.94", "10,878.94Cr", "10,878.94 Dr"

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

def filter_lines(doc: fitz.Document) -> List[str]:
    out = []
    for pg in doc:
        for ln in pg.get_text("text").splitlines():
            s = ln.strip()
            if not s:
                continue
            if any(rx.match(s) for rx in HEADER_NOISE):
                continue
            out.append(s)
    return out

def parse_balances_text(text: str) -> Tuple[Optional[float], Optional[float]]:
    num = r"\d{1,3}(?:,\d{3})*\.\d{2}"
    rx_open = re.compile(rf"Opening\s*Balance.*?({num})\s*([Cc][Rr]|[Dd][Rr])?", re.S)
    rx_close = re.compile(rf"Closing\s*Balance.*?({num})\s*([Cc][Rr]|[Dd][Rr])?", re.S)
    def parse_one(rx):
        m = rx.search(text)
        if not m: return None
        val = float(m.group(1).replace(",", ""))
        tag = (m.group(2) or "CR").upper()
        return -abs(val) if tag == "DR" else abs(val)
    return parse_one(rx_open), parse_one(rx_close)

def parse_year(text: str) -> int:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else datetime.now().year

# ---- Type Classification (Income / Expense / Transfer) ----
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

def parse_transactions_from_lines(lines: List[str], year: int, opening: Optional[float]):
    txns: List[Tuple[datetime, str, float, Optional[float]]] = []
    leftovers: List[str] = []
    prev_running = opening

    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        m = DATE_RE.match(s)
        if not m:
            i += 1
            continue

        day, mon, rest = m.groups()
        mon3 = mon[:3].title()
        desc_parts = [rest.strip()] if rest else []

        # First numeric-with-cents after the date = AMOUNT (with optional Cr/Dr)
        j = i + 1
        amount = None
        runbal = None

        while j < n:
            t = lines[j].strip()
            if DATE_RE.match(t):
                break
            mnum = NUM_WITH_TAG.match(t)
            if mnum:
                a_val = float(mnum.group(1).replace(",", ""))
                a_tag = (mnum.group(2) or "").upper()
                amount = -a_val if a_tag == "DR" else a_val
                j += 1
                break
            else:
                if t:
                    desc_parts.append(t)
                j += 1

        # Next numeric-with-cents line (if present) = RUNNING BALANCE (with optional Cr/Dr)
        if amount is not None and j < n:
            t2 = lines[j].strip()
            mnum2 = NUM_WITH_TAG.match(t2)
            if mnum2:
                rb_val = float(mnum2.group(1).replace(",", ""))
                rb_tag = (mnum2.group(2) or "").upper()
                runbal = -rb_val if rb_tag == "DR" else rb_val
                j += 1

        if amount is None:
            leftovers.append(f"no amount after {s}")
            i = j
            continue

        # Prefer running-balance delta to determine the true signed amount (handles Amount without signs)
        amt = amount
        if (runbal is not None) and (prev_running is not None):
            amt = round(runbal - prev_running, 2)
            prev_running = runbal

        try:
            dt = datetime.strptime(f"{int(day):02d} {mon3} {year}", "%d %b %Y")
        except Exception:
            dt = None
        desc = " ".join(" ".join(desc_parts).split())
        txns.append((dt, desc, amt, runbal))
        i = j

    return txns, leftovers

def parse_file(path: str) -> Dict[str, Any]:
    doc = fitz.open(path)
    try:
        full_text = "\n".join(pg.get_text("text") for pg in doc)
        opening, closing = parse_balances_text(full_text)
        year = parse_year(full_text)
        lines = filter_lines(doc)
        txns, leftovers = parse_transactions_from_lines(lines, year, opening)
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
        txns: List[Tuple[datetime, str, float, Optional[float]]] = parsed["transactions"]
        opening = parsed["opening"]
        closing = parsed["closing"]

        # Build detailed rows with classification
        for dt, desc, amt, _runbal in txns:
            all_tx.append({
                "Statement": Path(file.name).stem,
                "Date": dt,
                "Description": desc,
                "Amount (ZAR)": round(amt, 2),
                "Type": classify_type(desc, amt),
            })

        net = round(sum(a for _, _, a, _ in txns), 2)
        expected = (round(opening, 2) + net) if opening is not None else None
        diff = (round(closing, 2) - expected) if (closing is not None and expected is not None) else None

        balance_rows.append({
            "Statement": Path(file.name).stem,
            "Opening Balance (ZAR)": None if opening is None else round(opening, 2),
            "Net Movement (ZAR)": net,
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