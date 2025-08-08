# streamlit_app.py

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
st.sidebar.markdown("**🐛 Parser version:** 2025-08-08-r1")

DEFAULT_PASSWORD = "changeme"

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
    Accepts:
      '1,234.56', 'R 1,234.56', '(1,234.56)', '-1,234.56', '1,234.56 CR', 'DR 1,234.56'
    Returns signed float (credits positive, debits negative by default).
    """
    s = raw.strip()
    # Pull CR/DR markers (prefix/suffix)
    cr = bool(re.search(r"\bCR\b", s, re.IGNORECASE))
    dr = bool(re.search(r"\bDR\b", s, re.IGNORECASE))

    # strip currency and CR/DR text
    s = re.sub(r"\b(CR|DR)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[Rr]\s*", "", s).strip()

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]

    s = s.replace(",", "")
    try:
        val = float(s)
    except Exception:
        raise ValueError(f"Unparseable amount: {raw}")

    # Default sign: debit negative, credit positive. If markers present, override.
    if cr:
        val = abs(val)
    elif dr:
        val = -abs(val)
    elif neg:
        val = -abs(val)

    return val


def try_parse_statement_year(text: str) -> Optional[int]:
    """
    Try several FNB-ish phrasings to lock the year (more stable than using 'today').
    """
    # e.g., "Statement Date : 12 Aug 2024"
    m = re.search(r"Statement\s*Date\s*:\s*\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # e.g., "Period: 01 Jul 2024 to 31 Jul 2024"
    m = re.search(r"\b(?:Period|From)\b.*?\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4}).*?\bto\b.*?(\d{4})", text, re.IGNORECASE)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return y2  # prefer ending year

    # e.g., "as at 31 July 2024"
    m = re.search(r"\bas\s+at\s+\d{1,2}\s+[A-Za-z]{3,}\s+(\d{4})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    return None


def tokenize_lines(doc: fitz.Document) -> List[str]:
    """
    Use page.get_text('text') but strip obvious non-transaction noise.
    Keep order.
    """
    lines: List[str] = []
    for page in doc:
        for ln in page.get_text("text").splitlines():
            s = ln.strip()
            if is_noise(s):
                continue
            lines.append(s)
    # collapse duplicate blank clusters
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
DATE_START_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3})\b(.*)$", re.IGNORECASE)
AMOUNT_TAIL_RE = re.compile(
    r"""^
    (?:
        (?:[Rr]\s*)?                # optional 'R'
        (\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?)  # amount, with optional parens or leading minus
        (?:\s*(?:CR|DR))?           # optional CR/DR suffix
      |
        (?:CR|DR)\s*
        (\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?)  # amount with CR/DR prefix
    )
    $""",
    re.VERBOSE,
)


def parse_transactions_from_lines(lines: List[str], year: int) -> Tuple[List[Tuple[datetime, str, float]], List[str]]:
    """
    Transaction structure seen on many FNB PDFs:
      - Transaction starts with "DD MMM ..." (date + rest-of-line description)
      - Description may wrap multiple lines
      - Amount appears alone on the last line of the block (right-justified in the PDF)
    Returns (transactions, unparsed_candidate_lines)
    """
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
            # Not actually a transaction line, keep scanning
            i += 1
            continue

        # Build the wrapped description until we hit an amount line or next date
        desc_parts = []
        if rest:
            desc_parts.append(rest.strip())

        j = i + 1
        amount_line = None
        while j < n:
            cand = lines[j].strip()
            # next transaction starts?
            if DATE_START_RE.match(cand):
                break

            # Is this the amount tail?
            m_amt = AMOUNT_TAIL_RE.match(cand)
            if m_amt:
                amount_line = cand
                break

            # Otherwise it's part of the description
            if cand:
                desc_parts.append(cand)
            j += 1

        # Attempt to commit a transaction
        if amount_line:
            # Normalize description (squash inner spaces)
            desc = " ".join(" ".join(desc_parts).split())
            # Extract numeric from amount_line using a tolerant grab
            # Prefer suffix-form group(1), else prefix-form group(2)
            m_amt = AMOUNT_TAIL_RE.match(amount_line)
            raw_amt = m_amt.group(1) or m_amt.group(2)
            # Re-attach CR/DR text for sign calc
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

            # advance past amount line
            i = j + 1
        else:
            # Could not find terminating amount before next date/new section
            snippet = " | ".join([line] + lines[i+1:j])
            leftovers.append(f"[UNTERMINATED] {snippet[:240]}")
            i = j  # start from next candidate

    return txns, leftovers


BALANCE_RE = re.compile(
    r"""
    \b(Opening|Closing)\s*balance\b
    (?:\s*(?:as\s*at)?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}))?
    [\s:]*[Rr]?\s*
    (\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?)
    (?:\s*(CR|DR))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

ALT_CLOSING_RE = re.compile(
    r"""
    \b(?:Available|Current)\s*balance\b
    (?:\s*(?:as\s*at)?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}))?
    [\s:]*[Rr]?\s*
    (\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?)
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


def parse_file(path: str) -> Dict[str, Any]:
    doc = fitz.open(path)
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


# ---------------- Streamlit App ----------------
def main():
    st.title("📑 FNB Bank Statement Analyzer")

    pwd = st.sidebar.text_input("Password", type="password")
    if pwd != DEFAULT_PASSWORD:
        st.sidebar.warning("Enter the password to proceed")
        st.stop()

    uploaded = st.file_uploader(
        "Upload FNB bank statement PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )

    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_rows = []
    all_tx = []

    show_leftovers = st.sidebar.checkbox("Show unparsed candidate lines", value=True)

    for file in uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        parsed = parse_file(tmp_path)
        txns: List[Tuple[datetime, str, float]] = parsed["transactions"]
        opening = parsed["opening"]
        closing = parsed["closing"]

        # Net movement from parsed transactions
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

        for dt, desc, amt in txns:
            all_tx.append({
                "Statement": Path(file.name).stem,
                "Date": dt,
                "Description": desc,
                "Amount (ZAR)": round(amt, 2)
            })

        # Diagnostics panel per statement
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
                    st.write("No leftover candidates (good sign).")

    # Detailed transactions
    st.subheader("Detailed Transactions")
    if all_tx:
        df_tx = pd.DataFrame(all_tx).sort_values(["Statement", "Date"]).reset_index(drop=True)
        st.dataframe(df_tx, use_container_width=True)
    else:
        st.info("No transactions parsed yet.")

    # Balance reconciliation
    st.subheader("Balance Reconciliation Summary")
    df_bal = pd.DataFrame(balance_rows)
    if not df_bal.empty:
        st.dataframe(df_bal, use_container_width=True)
        any_diff = df_bal["Difference (ZAR)"].notna() & (df_bal["Difference (ZAR)"].abs() > 0.01)
        if any_diff.any():
            st.warning("Some statements have differences. Expand Diagnostics above and check **Unparsed candidate lines** for the culprits.")
        else:
            st.success("All statements reconcile (Expected Closing == Actual Closing).")
    else:
        st.info("No balances to show yet.")


if __name__ == "__main__":
    main()