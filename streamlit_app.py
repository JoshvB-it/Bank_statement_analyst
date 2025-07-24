# -------------------- Part 1 --------------------
import os
import re
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

DEFAULT_PASSWORD = "changeme"

CATEGORY_KEYWORDS = {
    "Income": [
        "pwc", "krans", "stefani"
    ],
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
        "pizza", "steers", "galitos", "burger", "chips", "dlocal *microsoft x"
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
    "Bank Charges & Fees": [
        "byc debit", "service fee", "bank charge", "interest",
        "facility fee", "admin fee"
    ],
}

def get_statement_year(path: str) -> Optional[int]:
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

# The remaining parts will be added below...

# -------------------- Part 2 --------------------
def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    year = get_statement_year(path) or datetime.now().year
    transactions = []
    date_pattern = r"^(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$"
    number_pattern = r"^(\d{1,3}(?:,\d{3})*\.\d{2})([A-Za-z]{2})?$"
    try:
        doc = fitz.open(path)
        for page in doc:
            lines = [line.strip() for line in page.get_text().split("\n")]
            i = 0
            while i < len(lines):
                line = lines[i]
                m = re.match(date_pattern, line)
                if m:
                    day, mon, remainder = m.group(1), m.group(2), m.group(3)
                    desc, amount = "", None
                    search_start = i + 1
                    if remainder:
                        desc = remainder.strip()
                    else:
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            mnum = re.match(number_pattern, next_line)
                            if mnum:
                                amount = float(mnum.group(1).replace(",", ""))
                                if mnum.group(2) and mnum.group(2).lower().startswith("cr"):
                                    amount = -amount
                                i += 1
                            else:
                                desc = next_line
                                search_start += 1
                    if amount is None:
                        for j in range(search_start, min(search_start + 6, len(lines))):
                            cand = lines[j].strip()
                            mnum = re.match(number_pattern, cand)
                            if mnum:
                                amount = float(mnum.group(1).replace(",", ""))
                                if mnum.group(2) and mnum.group(2).lower().startswith("cr"):
                                    amount = -amount
                                break
                    if amount is not None:
                        try:
                            dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                        except Exception:
                            dt = None
                        transactions.append((dt, desc, amount))
                i += 1
    except Exception:
        pass
    return transactions

# -------------------- Part 3 --------------------
def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    opening = None
    closing = None
    try:
        doc = fitz.open(path)
    except Exception:
        return (opening, closing)
    pattern = re.compile(r"(Opening|Closing) Balance\s+([\d,]+\.\d{2})\s*(Cr|Dr)?", re.IGNORECASE)
    for page in doc:
        text = page.get_text()
        for match in pattern.finditer(text):
            label, num_str, suffix = match.groups()
            amount = float(num_str.replace(",", ""))
            if suffix and suffix.lower().startswith("dr"):
                amount = -amount
            if label.lower().startswith("opening"):
                opening = amount
            elif label.lower().startswith("closing"):
                closing = amount
        if opening is not None and closing is not None:
            break
    return (opening, closing)


def classify_transaction(description: str, amount: float) -> str:
    desc_lower = description.lower() if description else ""
    if amount < 0:
        for keyword in CATEGORY_KEYWORDS.get("Income", []):
            if keyword in desc_lower:
                return "Income"
        return "Transfers"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "Income":
            continue
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return "Other"


def load_transactions_from_files(files: List) -> Tuple[pd.DataFrame, pd.DataFrame]:
    all_txns = []
    balance_rows = []
    for uploaded_file in files:
        data = uploaded_file.getvalue()
        tmp_path = f"/tmp/{uploaded_file.name}"
        with open(tmp_path, "wb") as tmpf:
            tmpf.write(data)
        txns = parse_transactions(tmp_path)
        opening, closing = parse_balances(tmp_path)
        for (dt, desc, amt) in txns:
            all_txns.append((uploaded_file.name, dt, desc, amt))
        total_transactions = sum(amt for _, _, amt in txns)
        expected_closing = None
        diff = None
        if opening is not None:
            expected_closing = opening + total_transactions
            if closing is not None:
                diff = closing - expected_closing
        balance_rows.append((
            uploaded_file.name,
            opening,
            total_transactions,
            expected_closing,
            closing,
            diff
        ))
    tx_df = pd.DataFrame(all_txns, columns=["Statement", "Date", "Description", "Amount"])
    if tx_df.empty:
        return tx_df, pd.DataFrame(balance_rows, columns=[
            "Statement", "Opening Balance", "Sum of Transactions",
            "Expected Closing", "Actual Closing", "Difference"
        ])
    tx_df["Category"] = tx_df.apply(lambda row: classify_transaction(row["Description"], row["Amount"]), axis=1)
    tx_df["Year"] = tx_df["Date"].dt.year
    tx_df["Month"] = tx_df["Date"].dt.strftime("%b")
    balance_df = pd.DataFrame(balance_rows, columns=[
        "Statement", "Opening Balance", "Sum of Transactions",
        "Expected Closing", "Actual Closing", "Difference"
    ])
    return tx_df, balance_df

# -------------------- Part 4 --------------------
def build_export_dataframe(tx_df: pd.DataFrame) -> pd.DataFrame:
    if tx_df.empty:
        return pd.DataFrame(columns=["Month-Year", "Category", "Amount", "YTD Total"])
    df = tx_df.copy()
    df["Month-Year"] = df["Date"].dt.to_period("M").astype(str)
    grouped = df.groupby(["Month-Year", "Category"])["Amount"].sum().reset_index()
    grouped["Month_Order"] = pd.to_datetime(grouped["Month-Year"] + "-01")
    def category_order(cat: str) -> Tuple[int, str]:
        if cat == "Income":
            return (0, cat)
        if cat == "Transfers":
            return (1, cat)
        return (2, cat)
    grouped["Cat_Order"] = grouped["Category"].apply(category_order)
    grouped = grouped.sort_values(["Month_Order", "Cat_Order"])
    grouped["YTD Total"] = grouped["Amount"].cumsum()
    grouped = grouped.drop(columns=["Month_Order", "Cat_Order"])
    grouped = grouped[["Month-Year", "Category", "Amount", "YTD Total"]]
    return grouped


def show_dashboard(tx_df: pd.DataFrame, balance_df: pd.DataFrame) -> None:
    st.subheader("Balance Check per Statement")
    if not balance_df.empty:
        formatted = balance_df.copy()
        for col in ["Opening Balance", "Sum of Transactions", "Expected Closing", "Actual Closing", "Difference"]:
            formatted[col] = formatted[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")
        st.dataframe(formatted)
    else:
        st.info("No balance data available.")

    st.subheader("Summary of Spending and Income")
    summary = tx_df.groupby("Category")["Amount"].sum().reset_index()
    summary = summary.sort_values("Amount", ascending=False)
    st.dataframe(summary.rename(columns={"Amount": "Total (ZAR)"}))

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

    st.subheader("Year‑to‑Date Totals")
    current_year = datetime.now().year
    ytd_df = tx_df[tx_df["Year"] == current_year]
    if not ytd_df.empty:
        ytd_summary = ytd_df.groupby("Category")["Amount"].sum().reset_index()
        ytd_summary = ytd_summary.sort_values("Amount", ascending=False)
        st.dataframe(ytd_summary.rename(columns={"Amount": "YTD Total (ZAR)"}))
    else:
        st.info("No transactions found for the current year.")

    st.subheader("Monthly Spending/Income")
    monthly = tx_df.copy()
    monthly["Month-Year"] = monthly["Date"].dt.to_period("M").astype(str)
    monthly_summary = monthly.groupby(["Month-Year"])["Amount"].sum().reset_index().sort_values("Month-Year")
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

    st.subheader("Export Monthly Classification with YTD Totals")
    export_df = build_export_dataframe(tx_df)
    csv_data = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download monthly breakdown (CSV)",
        data=csv_data,
        file_name="monthly_breakdown.csv",
        mime="text/csv"
    )

    st.subheader("Transactions")
    st.dataframe(tx_df.sort_values(["Date", "Statement"]))


def require_login() -> bool:
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
    st.set_page_config(page_title="FNB Statement Analysis", layout="wide")
    st.title("FNB Bank Statement Analysis")
    if not require_login():
        st.stop()
    st.write("Upload one or more PDF statements. The app will extract your transactions, categorise them automatically and provide a summary dashboard.")
    uploaded_files = st.file_uploader("Upload PDF statements", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        try:
            tx_df, balance_df = load_transactions_from_files(uploaded_files)
            if tx_df.empty:
                st.warning("No transactions were found in the uploaded files.")
            else:
                show_dashboard(tx_df, balance_df)
        except Exception as e:
            st.error(f"An error occurred while processing your files: {e}")
    else:
        st.info("Please upload at least one PDF statement to begin analysis.")

if __name__ == "__main__":
    main()