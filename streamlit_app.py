import streamlit as st
import pandas as pd
from parse_pdf import extract_transactions_from_pdf
from classify import classify_transaction
from config import APP_PASSWORD

# --- PASSWORD ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pwd = st.text_input("Enter password", type="password")
    if pwd == APP_PASSWORD:
        st.session_state.authenticated = True
    else:
        st.stop()

# --- FILE UPLOAD ---
st.title("📊 Personal Bank Statement Analyzer")
uploaded_files = st.file_uploader("Upload your monthly FNB bank statement PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = pd.DataFrame()

    for pdf in uploaded_files:
        df = extract_transactions_from_pdf(pdf)
        df["Category"] = df["Description"].apply(classify_transaction)
        all_data = pd.concat([all_data, df])

    # Add Budget Comparison
    budget = {
        "Airtime": 300,
        "Electricity": 600,
        "Fixed Expenses": 10000,
        "Food": 6000,
        "Transport": 4000,
        "Income - Salary": 0,
        "Income - Interest": 0,
        "Other": 2000
    }

    summary = all_data.groupby("Category")["Amount"].sum().reset_index()
    summary["Budget"] = summary["Category"].map(budget)
    summary["Variance"] = summary["Budget"] - summary["Amount"]

    st.success("✅ Parsed and classified successfully.")
    st.subheader("💡 Year-to-Date Summary vs Budget")
    st.dataframe(summary)

    st.subheader("📄 Full Transaction History")
    st.dataframe(all_data)

    # Download
    @st.cache_data
    def convert_df_to_excel(df1, df2):
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df1.to_excel(writer, index=False, sheet_name="Transactions")
            df2.to_excel(writer, index=False, sheet_name="Summary")
        return output.getvalue()

    excel_file = convert_df_to_excel(all_data, summary)
    st.download_button("📥 Download Excel", excel_file, file_name="classified_transactions.xlsx")

else:
    st.info("👆 Upload one or more monthly FNB PDFs to begin.")