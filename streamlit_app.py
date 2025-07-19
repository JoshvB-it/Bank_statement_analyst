import streamlit as st
import pandas as pd
from parse_pdf import parse_bank_statement
from classify import classify_transaction
from config import PASSWORD, BUDGET

st.set_page_config(page_title="Personal Finance Dashboard", layout="wide")

# Password protection
if "authenticated" not in st.session_state:
    password = st.text_input("Enter password", type="password")
    if password == PASSWORD:
        st.session_state.authenticated = True
        st.rerun()
    else:
        st.stop()

# File upload
st.title("📄 Upload Bank Statements")
uploaded_files = st.file_uploader("Browse files", type="pdf", accept_multiple_files=True)

all_data = []

if uploaded_files:
    for uploaded_file in uploaded_files:
        transactions = parse_bank_statement(uploaded_file)
        for tx in transactions:
            tx["Category"] = classify_transaction(tx["Description"])
        all_data.extend(transactions)

    if all_data:
        df = pd.DataFrame(all_data)
        df["Date"] = pd.to_datetime(df["Date"])
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
        df["Amount"] = df["Amount"].astype(float)

        st.subheader("🧾 Transactions")
        st.dataframe(df[["Date", "Description", "Amount", "Category"]])

        # Year-to-Date summary
        st.subheader("📈 Year-to-Date Summary by Category")
        ytd_summary = df.groupby("Category")["Amount"].sum().reset_index()
        st.dataframe(ytd_summary)

        # Budget comparison
        st.subheader("💰 Budget Comparison")
        budget_df = pd.DataFrame.from_dict(BUDGET, orient="index", columns=["Budget"])
        budget_df.index.name = "Category"
        comparison = budget_df.join(ytd_summary.set_index("Category"), how="left").fillna(0)
        comparison.rename(columns={"Amount": "Actual"}, inplace=True)
        comparison["Variance"] = comparison["Budget"] - comparison["Actual"]
        st.dataframe(comparison)

        # Export
        st.download_button("📥 Download Excel", data=df.to_csv(index=False), file_name="transactions.csv")

    else:
        st.warning("No transactions found in uploaded statements.")