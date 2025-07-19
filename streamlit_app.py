import streamlit as st
import pandas as pd
from io import BytesIO
from parse_pdf import parse_fnb_pdf
from classify import classify_transactions

# --- Password protection ---
PASSWORD = "secure123"  # change this
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("Enter password", type="password")
    if password == PASSWORD:
        st.session_state.authenticated = True
        st.rerun()
    else:
        st.stop()

# --- Upload ---
st.title("📄 Bank Statement Analyzer")
st.write("Upload your monthly FNB bank statements (PDF only).")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []

    for file in uploaded_files:
        text = parse_fnb_pdf(file)
        df = classify_transactions(text)
        df["Source"] = file.name
        all_data.append(df)

    final_df = pd.concat(all_data, ignore_index=True)

    # --- Budget and YTD summary ---
    st.header("📊 Dashboard")
    total_expense = final_df[final_df["Type"] == "Expense"]["Amount"].sum()
    total_income = final_df[final_df["Type"] == "Income"]["Amount"].sum()

    col1, col2 = st.columns(2)
    col1.metric("💰 Total Income YTD", f"R {total_income:,.2f}")
    col2.metric("📉 Total Expenses YTD", f"R {total_expense:,.2f}")

    st.subheader("Classified Transactions")
    st.dataframe(final_df)

    # --- Download Excel ---
    def convert_df(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()

    excel_data = convert_df(final_df)
    st.download_button("📥 Download Excel", excel_data, file_name="transactions.xlsx")

else:
    st.info("Please upload at least one PDF file.")