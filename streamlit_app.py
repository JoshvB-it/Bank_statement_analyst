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
    "Groceries": ["woolworths", "checkers", "pick n pay", "spar"],
    "Health & Pharmacy": ["clicks", "dis-chem", "pharmacy"],
    "Clothing & Accessories": ["mr price", "edgars", "pep", "sportscene"],
    "Food & Drink": ["kfc", "mcd", "burger", "pizza", "restaurant", "coffee"],
    "Fuel & Transport": ["engen", "sasol", "bp", "shell", "uber", "bolt"],
    "Entertainment & Digital": ["spotify", "netflix", "disney", "apple.com", "showmax"],
    "Education & School": ["laerskool", "school", "fees", "uniform"],
    "Bank Charges & Fees": ["service fee", "bank charge", "interest"],
}

def get_statement_year(path: str) -> Optional[int]:
    try:
        doc = fitz.open(path)
        for page in doc:
            text = page.get_text()
            m = re.search(r"Statement Date\\s*:\\s*\\d{1,2} [A-Za-z]+ (\\d{4})", text)
            if m:
                return int(m.group(1))
            break
    except Exception:
        return None
    return None

def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    year = get_statement_year(path) or datetime.now().year
    transactions = []
    date_pattern = r"^(\\d{1,2})\\s+([A-Za-z]{3})(?:\\s+(.+))?$"
    number_pattern = r"^(\\d{1,3}(?:,\\d{3})*\\.\\d{2})([A-Za-z]{2})?$"
    doc = fitz.open(path)
    for page in doc:
        lines = [line.strip() for line in page.get_text().split("\\n")]
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(date_pattern, line)
            if m:
                day, mon, remainder = m.group(1), m.group(2), m.group(3)
                desc = remainder.strip() if remainder else lines[i + 1]
                for j in range(i+1, i+6):
                    if j < len(lines):
                        cand = lines[j]
                        n = re.match(number_pattern, cand)
                        if n:
                            amt = float(n.group(1).replace(",", ""))
                            if n.group(2) and n.group(2).lower().startswith("cr"):
                                amt = -amt
                            try:
                                date_obj = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                                transactions.append((date_obj, desc, amt))
                            except:
                                pass
                            break
            i += 1
    return transactions
    def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    opening = None
    closing = None
    doc = fitz.open(path)
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
    desc = description.lower() if description else ""
    amt = round(amount, 2)

    # INCOME
    if amt < 0:
        if any(name in desc for name in ["pwc", "krans", "stefani"]):
            return "Income"
        return "Transfers"

    # INVESTMENTS
    if "bx90dx7yn" in desc:
        return "Investments - Crypto"
    if ("fnb" in desc or "allan gray" in desc):
        if amt == 1500:
            return "Investments - Retirement"
        elif amt == 1000:
            return "Investments - Tax-Free"

    # OTHER CATEGORIES
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in desc for keyword in keywords):
            return category

    return "Other"

def load_transactions_from_files(files: List) -> Tuple[pd.DataFrame, pd.DataFrame]:
    all_txns = []
    balance_rows = []
    for uploaded_file in files:
        tmp_path = f"/tmp/{uploaded_file.name}"
        with open(tmp_path, "wb") as f:
            f.write(uploaded_file.getvalue())

        txns = parse_transactions(tmp_path)
        opening, closing = parse_balances(tmp_path)
        total = sum([amt for _, _, amt in txns])
        expected_closing = opening + total if opening is not None else None
        diff = closing - expected_closing if closing and expected_closing else None

        for dt, desc, amt in txns:
            all_txns.append((uploaded_file.name, dt, desc, amt))

        balance_rows.append((
            uploaded_file.name, opening, total, expected_closing, closing, diff
        ))

    tx_df = pd.DataFrame(all_txns, columns=["Statement", "Date", "Description", "Amount"])
    if not tx_df.empty:
        tx_df["Category"] = tx_df.apply(lambda row: classify_transaction(row["Description"], row["Amount"]), axis=1)
        tx_df["Year"] = tx_df["Date"].dt.year
        tx_df["Month"] = tx_df["Date"].dt.strftime("%b")

    balance_df = pd.DataFrame(balance_rows, columns=[
        "Statement", "Opening Balance", "Sum of Transactions",
        "Expected Closing", "Actual Closing", "Difference"
    ])
    return tx_df, balance_df
    def show_dashboard(tx_df: pd.DataFrame, balance_df: pd.DataFrame) -> None:
    st.subheader("📊 Balance Check per Statement")
    if not balance_df.empty:
        formatted = balance_df.copy()
        for col in ["Opening Balance", "Sum of Transactions", "Expected Closing", "Actual Closing", "Difference"]:
            formatted[col] = formatted[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")
        st.dataframe(formatted)
    else:
        st.info("No balance data available.")

    st.subheader("📌 Summary of Spending and Income")
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

    st.subheader("📆 Year-to-Date Totals")
    current_year = datetime.now().year
    ytd_df = tx_df[tx_df["Year"] == current_year]
    if not ytd_df.empty:
        ytd_summary = ytd_df.groupby("Category")["Amount"].sum().reset_index()
        ytd_summary = ytd_summary.sort_values("Amount", ascending=False)
        st.dataframe(ytd_summary.rename(columns={"Amount": "YTD Total (ZAR)"}))
    else:
        st.info("No transactions found for the current year.")

    st.subheader("📅 Monthly Spend vs Income")
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

    st.subheader("📁 Export Monthly Breakdown with YTD")
    export_df = build_export_dataframe(tx_df)
    csv_data = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📤 Download Monthly Breakdown CSV",
        data=csv_data,
        file_name="monthly_breakdown.csv",
        mime="text/csv"
    )

    st.subheader("🧾 All Transactions")
    st.dataframe(tx_df.sort_values(["Date", "Statement"]))


def build_export_dataframe(tx_df: pd.DataFrame) -> pd.DataFrame:
    if tx_df.empty:
        return pd.DataFrame(columns=["Month-Year", "Category", "Amount", "YTD Total"])
    df = tx_df.copy()
    df["Month-Year"] = df["Date"].dt.to_period("M").astype(str)
    grouped = df.groupby(["Month-Year", "Category"])["Amount"].sum().reset_index()
    grouped["Month_Order"] = pd.to_datetime(grouped["Month-Year"] + "-01")

    def category_sort_key(cat: str) -> Tuple[int, str]:
        if cat == "Income": return (0, cat)
        if "Investments" in cat: return (1, cat)
        if "Debit Order" in cat: return (2, cat)
        if cat in ["Groceries", "Fuel & Transport", "Food & Drink", "Clothing & Accessories",
                   "Health & Pharmacy", "Entertainment & Digital", "Education & School", "Bank Charges & Fees"]:
            return (3, cat)
        if cat == "Transfers": return (4, cat)
        return (5, cat)

    grouped["Cat_Order"] = grouped["Category"].apply(category_sort_key)
    grouped = grouped.sort_values(["Month_Order", "Cat_Order"])
    grouped["YTD Total"] = grouped["Amount"].cumsum()
    grouped = grouped.drop(columns=["Month_Order", "Cat_Order"])
    return grouped[["Month-Year", "Category", "Amount", "YTD Total"]]
    def require_login() -> bool:
    """Simple password prompt. Returns True if the user is authorised."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.header("🔐 Login Required")
    password = st.text_input("Enter password", type="password")
    if password:
        expected = os.getenv("APP_PASSWORD", DEFAULT_PASSWORD)
        if password == expected:
            st.session_state.authenticated = True
            st.success("✅ Logged in successfully.")
            return True
        else:
            st.error("❌ Incorrect password. Please try again.")
    return False


def main() -> None:
    """Main entry point for the Streamlit app."""
    st.set_page_config(page_title="FNB Statement Analysis", layout="wide")
    st.title("📄 FNB Bank Statement Analysis")
    if not require_login():
        st.stop()

    st.write(
        "Upload one or more FNB PDF bank statements. "
        "Transactions will be extracted, auto-categorised, and shown in a live dashboard with monthly & YTD breakdowns."
    )
    uploaded_files = st.file_uploader(
        "📎 Upload PDF bank statements", type=["pdf"], accept_multiple_files=True
    )

    if uploaded_files:
        try:
            tx_df, balance_df = load_transactions_from_files(uploaded_files)
            if tx_df.empty:
                st.warning("⚠️ No transactions were found in the uploaded files.")
            else:
                show_dashboard(tx_df, balance_df)
        except Exception as e:
            st.error(f"🚫 An error occurred while processing your files: {e}")
    else:
        st.info("⬆️ Please upload at least one PDF statement to begin analysis.")


if __name__ == "__main__":
    main()
    