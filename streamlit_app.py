# streamlit_app.py

import os
import re
import tempfile
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

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
    """
    Reads the first page looking for 'Statement Date : DD MMM YYYY' to extract year.
    """
    try:
        doc = fitz.open(path)
        for page in doc:
            text = page.get_text()
            m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
            if m:
                return int(m.group(1))
            break
    except Exception:
        return None
    return None


def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    """
    Finds lines like:
      26 Jul Groceries at Woolworths    1,234.56Cr
      27 Jul Uber ride                   123.45Dr
    and pulls out date, description & signed amount in one go.
    """
    transactions: List[Tuple[datetime, str, float]] = []
    year = get_statement_year(path) or datetime.now().year

    # Regex to match: day, mon, description, number, optional Cr/Dr
    line_re = re.compile(
        r'^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(.+?)\s+'
        r'(\d{1,3}(?:,\d{3})*\.\d{2})(?:\s*(Cr|Dr))?\s*$',
        re.IGNORECASE
    )

    try:
        doc = fitz.open(path)
        for page in doc:
            for raw in page.get_text("text").splitlines():
                m = line_re.match(raw)
                if not m:
                    continue
                day, mon, desc, num_str, drcr = m.groups()
                amt = float(num_str.replace(",", ""))
                # default to debit (negative) if no 'Cr'
                if not drcr or not drcr.lower().startswith("cr"):
                    amt = -amt
                try:
                    dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                except ValueError:
                    continue
                transactions.append((dt, desc.strip(), amt))
    except Exception:
        # fail silently on corrupt or unreadable files
        pass

    return transactions


def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Scans for 'Opening Balance 12,345.67 Cr/Dr' and 'Closing Balance ...'
    """
    opening: Optional[float] = None
    closing: Optional[float] = None

    try:
        doc = fitz.open(path)
    except Exception:
        return opening, closing

    pattern = re.compile(
        r"(Opening|Closing) Balance\s+([\d,]+\.\d{2})\s*(Cr|Dr)?",
        re.IGNORECASE
    )
    for page in doc:
        text = page.get_text()
        for match in pattern.finditer(text):
            label, num_str, suffix = match.groups()
            amt = float(num_str.replace(",", ""))
            if suffix and suffix.lower().startswith("dr"):
                amt = -amt
            if label.lower().startswith("opening"):
                opening = amt
            else:
                closing = amt
        if opening is not None and closing is not None:
            break

    return opening, closing


def classify_transaction(description: str, amount: float) -> str:
    desc = (description or "").lower()

    # 1) Positive → Income or Transfers
    if amount > 0:
        for kw in CATEGORY_KEYWORDS["Income"]:
            if kw in desc:
                return "Income"
        return "Transfers"

    # 2) Match expense categories
    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat == "Income":
            continue
        for kw in kws:
            if kw in desc:
                return cat

    # 3) Fallback: small debits → Other, large debits → Uncategorized
    if abs(amount) <= 500:
        return "Other"
    return "Uncategorized"


def main():
    st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
    st.title("📑 FNB Bank Statement Analyzer")

    # Sidebar password
    pwd = st.sidebar.text_input("Password", type="password")
    if pwd != DEFAULT_PASSWORD:
        st.sidebar.warning("Enter the password to proceed")
        st.stop()

    uploaded = st.file_uploader(
        "Upload your FNB bank statement PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )
    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_data = []
    all_transactions = []

    for file in uploaded:
        # write to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        opening, closing = parse_balances(tmp_path)
        txns = parse_transactions(tmp_path)

        # compute expected closing
        expected = None
        if opening is not None:
            expected = opening + sum(amt for _, _, amt in txns)

        balance_data.append({
            "Statement": file.name,
            "Opening": opening,
            "Expected Closing": expected,
            "Actual Closing": closing,
            "Difference": (closing - expected) if (closing is not None and expected is not None) else None
        })

        for dt, desc, amt in txns:
            all_transactions.append((dt, desc, amt, file.name))

    # Balance check table
    st.subheader("Balance Check per Statement")
    df_bal = pd.DataFrame(balance_data)
    st.dataframe(
        df_bal[["Statement", "Opening", "Expected Closing", "Actual Closing", "Difference"]],
        use_container_width=True
    )

    # Transactions & categorization
    df_tx = pd.DataFrame(
        all_transactions,
        columns=["Date", "Description", "Amount", "Source"]
    )
    df_tx["Category"] = df_tx.apply(
        lambda r: classify_transaction(r.Description, r.Amount), axis=1
    )

    # Summary by category
    st.subheader("Summary of Spending and Income")
    summary = (
        df_tx.groupby("Category")["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "Total (ZAR)"})
        .sort_values("Total (ZAR)", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(summary, use_container_width=True)

    # Bar chart
    st.subheader("Spending by Category")
    chart = (
        alt.Chart(summary)
        .mark_bar()
        .encode(
            x=alt.X("Total (ZAR)", title="Amount (ZAR)"),
            y=alt.Y("Category", sort="-x"),
        )
        .properties(height=400)
    )
    st.altair_chart(chart, use_container_width=True)


if __name__ == "__main__":
    main()