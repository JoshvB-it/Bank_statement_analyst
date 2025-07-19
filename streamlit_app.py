import streamlit as st
import pandas as pd
from parse_pdf import parse_bank_statement
from classify import classify_transaction
from config import PASSWORD
from io import BytesIO

st.set_page_config(page_title="Private Finance Dashboard", layout="wide")

# Password protection
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pwd = st.text_input("Enter password", type="password")
    if pwd == PASSWORD:
        st.session_state.authenticated = True
    else:
        st.stop()

st.title("📄 Upload Bank Statements")
uploaded_files = st.file_uploader("Browse files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_transactions = pd.DataFrame()

    for file in uploaded_files:
        df = parse_bank_statement(file)
        if not df.empty:
            df["Category"] = df.apply(lambda row: classify_transaction(row["Description"], row["Amount"]), axis=1)
            all_transactions = pd.concat([all_transactions, df], ignore_index=True)

    if not all_transactions.empty:
        all_transactions["Date"] = pd.to_datetime(all_transactions["Date"])
        all_transactions.sort_values(by="Date", inplace=True)

        st.subheader("📊 Transactions")
        st.dataframe(all_transactions)

        ytd_summary = all_transactions.groupby("Category")["Amount"].sum().reset_index()

        st.subheader("📈 Year-to-Date Summary by Category")
        st.dataframe(ytd_summary)

        # Export to Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            all_transactions.to_excel(writer, sheet_name="Transactions", index=False)
            ytd_summary.to_excel(writer, sheet_name="YTD Summary", index=False)

        st.download_button(
            label="📥 Download Excel",
            data=output.getvalue(),
            file_name="finance_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.warning("⚠️ No transactions found in uploaded statements.")