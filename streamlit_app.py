# streamlit_app.py

import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

# Debug banner
st.sidebar.markdown("**🐛 Parser version:** 2025-07-27-v5")

DEFAULT_PASSWORD = "changeme"

CATEGORY_KEYWORDS = {
    "Income": ["pwc", "krans", "stefani", "salary", "bonus", "income", "deposit"],
    "Groceries": [
        "woolworths", "cc fresh", "fresh x", "pick n pay", "spar",
        "checkers", "food lovers", "pnp", "spaza", "fruit and veg"
    ],
    "Health & Pharmacy": ["clicks", "dis-chem", "pharmacy", "chemist", "clinic"],
    "Clothing & Accessories": [
        "mr price", "mrp", "takkie", "tekkie", "k jewels", "jeweller",
        "jewellery", "sheetstreet", "sportscene", "pep home", "pep",
        "edgars", "sport"
    ],
    "Food & Drink": [
        "bk ", "kfc", "mcd", "roco", "spur", "king pie", "mochachos",
        "milky lane", "salsa", "mama", "restaurant", "coffee", "diner",
        "pizza", "steers", "galitos", "burger", "chips"
    ],
    "Fuel & Transport": [
        "engen", "sasol", "bp", "caltex", "shell", "petrol", "diesel",
        "parking", "uber", "bolt"
    ],
    "Entertainment & Digital": [
        "spotify", "netflix", "apple.com", "microsoft", "play", "itunes",
        "book", "exclusive books", "gym", "movie", "cinema", "showmax",
        "hbomax", "disney", "amazon"
    ],
    "Education & School": [
        "laerskool", "school", "tuition", "netcash", "scholar", "fees",
        "uniform", "books"
    ],
    "Bank Charges & Fees": [
        "byc debit", "service fee", "bank charge", "interest",
        "facility fee", "admin fee"
    ],
}


def get_statement_year(path: str) -> Optional[int]:
    try:
        doc = fitz.open(path)
        for page in doc:
            text = page.get_text("text")
            m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    doc = fitz.open(path)
    lines: List[str] = []
    for page in doc:
        lines.extend(page.get_text("text").splitlines())

    year = get_statement_year(path) or datetime.now().year
    transactions: List[Tuple[datetime, str, float]] = []

    single_re = re.compile(
        r'^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(.+?)\s+'
        r'(\d{1,3}(?:,\d{3})*\.\d{2})(Cr|Dr)?\s*$',
        re.IGNORECASE
    )
    start_re = re.compile(
        r'^\s*(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$', 
        re.IGNORECASE
    )
    num_re = re.compile(r'^(\d{1,3}(?:,\d{3})*\.\d{2})(Cr|Dr)?$', re.IGNORECASE)

    i, n = 0, len(lines)
    while i < n:
        raw = lines[i].strip()
        m1 = single_re.match(raw)
        if m1:
            day, mon, desc, num_str, drcr = m1.groups()
            amt = float(num_str.replace(",", ""))
            if not drcr or not drcr.lower().startswith("cr"):
                amt = -amt
            try:
                dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                transactions.append((dt, desc.strip(), amt))
            except ValueError:
                pass
            i += 1
            continue

        m2 = start_re.match(raw)
        if m2:
            day, mon, rest = m2.groups()
            desc_lines = [rest.strip()] if rest else []
            j = i + 1
            found = False
            while j < n:
                nxt = lines[j].strip()
                if start_re.match(nxt):
                    break
                m3 = num_re.match(nxt)
                if m3:
                    num_str, drcr = m3.groups()
                    amt = float(num_str.replace(",", ""))
                    if not drcr or not drcr.lower().startswith("cr"):
                        amt = -amt
                    desc = " ".join(desc_lines).strip()
                    try:
                        dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                        transactions.append((dt, desc, amt))
                    except ValueError:
                        pass
                    found = True
                    break
                desc_lines.append(nxt)
                j += 1
            i = j + 1 if found else i + 1
            continue

        i += 1

    return transactions


def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    opening = None
    closing = None
    try:
        doc = fitz.open(path)
    except Exception:
        return opening, closing

    full_text = "\n".join(page.get_text("text") for page in doc)
    date_part = r"(?:as at\s*(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}))?"
    bal_re = re.compile(
        rf"(Opening|Closing)\s*balance\s*{date_part}[:\sRr]*([\d,]+\.\d{{2}})(?:\s*(Cr|Dr))?",
        re.IGNORECASE
    )
    for m in bal_re.finditer(full_text):
        label, num_str, suffix = m.groups()
        amt = float(num_str.replace(",", ""))
        if suffix and suffix.lower().startswith("dr"):
            amt = -amt
        if label.lower() == "opening":
            opening = amt
        else:
            closing = amt

    if closing is None:
        avail_re = re.compile(
            rf"(?:Available|Current)\s*balance\s*{date_part}[:\sRr]*([\d,]+\.\d{{2}})(?:\s*(Cr|Dr))?",
            re.IGNORECASE
        )
        m2 = avail_re.search(full_text)
        if m2:
            num_str, suffix = m2.groups()
            amt = float(num_str.replace(",", ""))
            if suffix and suffix.lower().startswith("dr"):
                amt = -amt
            closing = amt
            st.sidebar.warning(f"Fallback 'Available/Current balance' used: {closing:.2f}")

    return opening, closing


def main():
    st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
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
    all_txns: List[Tuple[datetime, str, float, str]] = []

    for file in uploaded:
        # save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        opening, closing = parse_balances(tmp_path)
        txns = parse_transactions(tmp_path)
        net_movement = sum(amt for _, _, amt in txns)
        expected_closing = (opening + net_movement) if opening is not None else None
        diff = (closing - expected_closing) if (closing is not None and expected_closing is not None) else None

        balance_rows.append({
            "Statement": Path(file.name).stem,
            "Opening Balance (ZAR)": opening,
            "Net Movement (ZAR)": net_movement,
            "Expected Closing (ZAR)": expected_closing,
            "Actual Closing (ZAR)": closing,
            "Difference (ZAR)": diff
        })

        for dt, desc, amt in txns:
            all_txns.append({
                "Statement": Path(file.name).stem,
                "Date": dt,
                "Description": desc,
                "Amount (ZAR)": amt
            })

    # Detailed transactions
    st.subheader("Detailed Transactions by Statement")
    df_tx = pd.DataFrame(all_txns)
    # round amounts to 2dp
    df_tx["Amount (ZAR)"] = df_tx["Amount (ZAR)"].round(2)
    st.dataframe(df_tx, use_container_width=True)

    # Balance reconciliation
    st.subheader("Balance Reconciliation Summary")
    df_bal = pd.DataFrame(balance_rows)
    for col in ["Opening Balance (ZAR)", "Net Movement (ZAR)", "Expected Closing (ZAR)", "Actual Closing (ZAR)", "Difference (ZAR)"]:
        df_bal[col] = df_bal[col].round(2)
    st.dataframe(df_bal, use_container_width=True)

    # (Optional) keep your category summary/chart below if you still want it
    # ...
    # st.subheader("Summary of Spending and Income")
    # [your existing summary code here]

if __name__ == "__main__":
    main()