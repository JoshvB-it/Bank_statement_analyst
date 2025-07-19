import streamlit as st
import pandas as pd
from parse_pdf import parse_bank_statement
from classify import classify_transactions
from config import PASSWORD, BUDGET

st.set_page_config(page_title="Private Personal Finance", layout="centered")

# Password protection
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("Enter password", type="password")
    if password == PASSWORD:
        st.session_state.authenticated = True
        st.rerun()
    else:
        st.stop()

# Main app
st.title("📊 Private Personal Finance Dashboard")
uploaded_files = st.file_uploader("Upload your FNB PDF bank statements", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for pdf in uploaded_files:
        df = parse_bank_statement(pdf)
        if not df.empty:
            df = classify_transactions(df)
            all_data.append(df)

    if all_data:
        df_all = pd.concat(all_data).sort_values(by="Date")
        df_all["Month"] = pd.to_datetime(df_all["Date"]).dt.to_period("M")

        # Monthly + YTD summary
        monthly_summary = df_all.groupby(["Month", "Category"])["Amount"].sum().unstack(fill_value=0)
        ytd_summary = df_all.groupby("Category")["Amount"].sum()

        # Budget comparison
        budget_df = pd.DataFrame.from_dict(BUDGET, orient="index", columns=["Budget"])
        budget_df["Actual YTD"] = ytd_summary
        budget_df["Variance"] = budget_df["Budget"] - budget_df["Actual YTD"]

        # Show summaries
        st.subheader("📅 Monthly Summary")
        st.dataframe(monthly_summary.style.format("R{:,.2f}"))

        st.subheader("📆 Year-to-Date Summary vs Budget")
        st.dataframe(budget_df.style.format("R{:,.2f}"))

        # Download
        st.download_button("⬇️ Download Full Transactions", df_all.to_csv(index=False), file_name="transactions.csv")

    else:
        st.error("No transactions parsed from PDFs.")