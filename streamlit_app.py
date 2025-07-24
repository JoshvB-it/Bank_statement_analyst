"""
Streamlit application for FNB bank statement analysis.

This app allows the user to upload one or more PDF bank statements and
automatically extracts the transactions contained in them.  The
extracted transactions are categorised into high‑level spending
categories (e.g. groceries, fuel, clothing, entertainment, etc.) based
on simple keyword matching.  The app then summarises your spending
and income by category, presents year‑to‑date totals and monthly
aggregations and displays an interactive dashboard with charts and
tables.

The app is protected by a simple password mechanism.  Only users who
know the password will be able to access the data upload and
dashboard.  To change the password you can set the ``APP_PASSWORD``
environment variable at deployment time or update the
``DEFAULT_PASSWORD`` constant below.

Dependencies:
  - streamlit
  - PyMuPDF (imported as ``fitz``)
  - pandas
  - altair

To run locally:

    pip install streamlit PyMuPDF pandas altair
    streamlit run app.py

When deploying on Streamlit Community Cloud, place this file in a
repository along with a ``requirements.txt`` specifying the
dependencies above.
"""

import os
import re
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
# Default password used if no environment variable is set.  You should
# override this via the ``APP_PASSWORD`` environment variable in your
# deployment settings or by modifying this constant in a private fork.
DEFAULT_PASSWORD = "changeme"


# Keyword dictionary for transaction classification.  Each key is a
# category and each value is a list of lowercase substrings which, if
# found in the transaction description, will assign that transaction
# to the given category.  You can extend or modify this dictionary to
# better match your own spending habits.
CATEGORY_KEYWORDS = {
    "Groceries": [
        "woolworths", "cc fresh", "fresh x", "pick n pay", "spar",
        "checkers", "food lovers", "pnp", "spaza", "fruit and veg"
    ],
    "Health & Pharmacy": [
        "clicks", "dis-chem", "pharmacy", "chemist", "clinic"
    ],
    "Clothing & Accessories": [
        "mr price", "mrp", "takkie", "tekkie", "k jewels", "jeweller",
        "jewellery", "sheetstreet", "sportscene", "pep home", "pep",
        "edgars", "sport",
    ],
    "Food & Drink": [
        "bk ", "kfc", "mcd", "roco", "spur", "king pie", "mochachos",
        "milky lane", "salsa", "mama", "restaurant", "coffee", "diner",
        "pizza", "steers", "galitos", "burger", "chips", "dlocal *microsoft x",  # digital services fall here by default
    ],
    "Fuel & Transport": [
        "engen", "sasol", "bp", "caltex", "shell", "petrol", "diesel",
        "parking", "uber", "bolt"
    ],
    "Entertainment & Digital": [
        "spotify", "netflix", "apple.com", "microsoft", "play",
        "itunes", "book", "gift acres", "exclusive books", "hokaai",
        "planet fitness", "yoga", "gym", "movie", "cinema", "showmax",
        "hbomax", "disney", "amazon"
    ],
    "Education & School": [
        "laerskool", "school", "tuition", "netcash", "scholar",
        "fees", "uniform", "books"
    ],
    "Transfers & Income": [
        "transfer", "payment", "salary", "credit", "magtape credit",
        "fnb app transfer", "received", "cr netcash"
    ],
    "Bank Charges & Fees": [
        "byc debit", "service fee", "bank charge", "interest",
        "facility fee", "admin fee"
    ],
}


def get_statement_year(path: str) -> Optional[int]:
    """Extract the statement year from the first page of the PDF.

    Bank statements list a "Statement Date" on the first page (e.g.
    "Statement Date : 14 May 2025").  We parse the year from this line.
    Returns None if no year can be determined.
    """
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    for page in doc:
        text = page.get_text()
        m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
        if m:
            return int(m.group(1))
        # only check the first page
        break
    return None


def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    """Parse all transactions from a PDF statement.

    Each transaction is returned as a tuple of (date, description,
    amount).  Debits (spending) are positive numbers and credits
    (income or transfers into the account) are negative numbers.  The
    parser handles multiple formats found in FNB bank statements.
    """
    year = get_statement_year(path) or datetime.now().year
    transactions: List[Tuple[datetime, str, float]] = []
    date_pattern = r"^(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$"
    number_pattern = r"^(\d{1,3}(?:,\d{3})*\.\d{2})([A-Za-z]{2})?$"
    try:
        doc = fitz.open(path)
    except Exception:
        return transactions
    for page in doc:
        lines = [line.strip() for line in page.get_text().split("\n")]
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(date_pattern, line)
            if m:
                day, mon, remainder = m.group(1), m.group(2), m.group(3)
                desc: str = ""
                amount: Optional[float] = None
                search_start = i + 1
                if remainder:
                    # date and description on the same line
                    desc = remainder.strip()
                    search_start = i + 1
                else:
                    # separate date; determine description or immediate amount
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # is next line a number? if so then description is blank
                        mnum = re.match(number_pattern, next_line)
                        if mnum:
                            desc = ""
                            num = float(mnum.group(1).replace(",", ""))
                            suffix = mnum.group(2)
                            if suffix and suffix.lower().startswith("cr"):
                                num = -num
                            amount = num
                            i = i + 1  # skip over amount line
                            search_start = i + 1
                        else:
                            # otherwise treat next line as description
                            desc = next_line
                            search_start = i + 2
                # if amount has not been set, search for it in subsequent lines
                if amount is None:
                    for j in range(search_start, min(search_start + 6, len(lines))):
                        cand = lines[j].strip()
                        mnum = re.match(number_pattern, cand)
                        if mnum:
                            num = float(mnum.group(1).replace(",", ""))
                            suffix = mnum.group(2)
                            if suffix and suffix.lower().startswith("cr"):
                                num = -num
                            amount = num
                            break
                if amount is not None:
                    try:
                        dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                    except Exception:
                        dt = None
                    transactions.append((dt, desc, amount))
            i += 1
    return transactions


def classify_transaction(description: str) -> str:
    """Classify a transaction into a high‑level spending category.

    The function looks for the presence of any keyword from the
    ``CATEGORY_KEYWORDS`` mapping in the lowercase description.  The
    first matching category is returned.  If no keywords match the
    description, the transaction is assigned to the "Other" category.
    """
    desc_lower = description.lower() if description else ""
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    # identify credits/income explicitly: descriptions with common
    # transfer or credit keywords but not matched above fall here
    if any(k in desc_lower for k in ["cr ", "credit", "transfer", "salary"]):
        return "Transfers & Income"
    return "Other"


def load_transactions_from_files(files: List) -> pd.DataFrame:
    """Load and combine transactions from multiple uploaded PDF files.

    Returns a DataFrame with columns: Date, Description, Amount,
    Category, Month, Year.  Dates that cannot be parsed will be
    represented as NaT.
    """
    all_txns: List[Tuple[datetime, str, float]] = []
    for uploaded_file in files:
        # Capture the raw bytes from the uploaded file
        data = uploaded_file.getvalue()
        tmp_path = f"/tmp/{uploaded_file.name}"
        with open(tmp_path, "wb") as tmpf:
            tmpf.write(data)
        txns = parse_transactions(tmp_path)
        all_txns.extend(txns)
    df = pd.DataFrame(all_txns, columns=["Date", "Description", "Amount"])
    if df.empty:
        return df
    df["Category"] = df["Description"].apply(classify_transaction)
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.strftime("%b")
    return df


def show_dashboard(df: pd.DataFrame) -> None:
    """Render interactive dashboard elements based on the transaction DataFrame."""
    st.subheader("Summary of Spending and Income")
    summary = df.groupby("Category")["Amount"].sum().reset_index()
    summary = summary.sort_values("Amount", ascending=False)
    st.dataframe(summary.rename(columns={"Amount": "Total (ZAR)"}))

    # Bar chart for spending categories (expenses > 0)
    spend_df = summary[summary["Amount"] > 0]
    if not spend_df.empty:
        chart = alt.Chart(spend_df).mark_bar().encode(
            x=alt.X("Category", sort='-y', title="Category"),
            y=alt.Y("Amount", title="Total Spend (ZAR)"),
            color=alt.Color("Category", legend=None),
            tooltip=["Category", "Amount"]
        ).properties(
            width=600, height=300, title="Spending by Category"
        )
        st.altair_chart(chart, use_container_width=True)

    # Year‑to‑date totals
    st.subheader("Year‑to‑Date Totals")
    current_year = datetime.now().year
    ytd_df = df[df["Year"] == current_year]
    if not ytd_df.empty:
        ytd_summary = ytd_df.groupby("Category")["Amount"].sum().reset_index()
        ytd_summary = ytd_summary.sort_values("Amount", ascending=False)
        st.dataframe(ytd_summary.rename(columns={"Amount": "YTD Total (ZAR)"}))
    else:
        st.info("No transactions found for the current year.")

    # Monthly totals
    st.subheader("Monthly Spending/Income")
    monthly = df.copy()
    monthly["Month-Year"] = monthly["Date"].dt.to_period("M").astype(str)
    monthly_summary = monthly.groupby(["Month-Year"])["Amount"].sum().reset_index()
    monthly_summary["Spend"] = monthly_summary["Amount"].apply(lambda x: x if x > 0 else 0)
    monthly_summary["Income"] = monthly_summary["Amount"].apply(lambda x: -x if x < 0 else 0)
    melted = monthly_summary.melt(id_vars=["Month-Year"], value_vars=["Spend", "Income"],
                                   var_name="Type", value_name="Value")
    chart2 = alt.Chart(melted).mark_bar().encode(
        x=alt.X("Month-Year", sort=None, title="Month"),
        y=alt.Y("Value", title="Amount (ZAR)"),
        color=alt.Color("Type", scale=alt.Scale(domain=["Spend", "Income"], range=['#E4572E', '#4C78A8'])),
        tooltip=["Month-Year", "Type", "Value"]
    ).properties(width=600, height=300, title="Monthly Spend vs Income")
    st.altair_chart(chart2, use_container_width=True)

    # Display raw transactions
    st.subheader("Transactions")
    st.dataframe(df.sort_values("Date"))


def require_login() -> bool:
    """Simple password prompt. Returns True if the user is authorised."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.header("Login")
    password = st.text_input("Enter password", type="password")
    if password:
        expected = os.getenv("APP_PASSWORD", DEFAULT_PASSWORD)
        if password == expected:
            st.session_state.authenticated = True
            st.success("Logged in successfully.")
            return True
        else:
            st.error("Incorrect password. Please try again.")
    return False


def main() -> None:
    """Main entry point for the Streamlit app."""
    st.set_page_config(page_title="FNB Statement Analysis", layout="wide")
    st.title("FNB Bank Statement Analysis")
    # Enforce login
    if not require_login():
        st.stop()
    st.write(
        "Upload one or more PDF statements. The app will extract your transactions, "
        "categorise them automatically and provide a summary dashboard."
    )
    uploaded_files = st.file_uploader(
        "Upload PDF statements", type=["pdf"], accept_multiple_files=True
    )
    if uploaded_files:
        try:
            df = load_transactions_from_files(uploaded_files)
            if df.empty:
                st.warning("No transactions were found in the uploaded files.")
            else:
                show_dashboard(df)
        except Exception as e:
            st.error(f"An error occurred while processing your files: {e}")
    else:
        st.info("Please upload at least one PDF statement to begin analysis.")


if __name__ == "__main__":
    main()