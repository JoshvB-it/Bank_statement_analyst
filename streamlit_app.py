# streamlit_app.py

import streamlit as st
import pandas as pd
from io import BytesIO
from config import PASSWORD
from parse_pdf import parse_bank_statement
from classify import classify_dataframe

st.set_page_config(page_title="Private Finance App", layout="wide")

# 🔒 Password gate
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("Enter password", type="password")
    if password == PASSWORD:
        st.session_state.authenticated = True
        st.rerun()
    else:
        st.stop()

# ✅ Main app starts here
st.title("📊 Personal Finance Dashboard")

uploaded_files = st.file_uploader("Upload PDF bank statements", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []

    for file in uploaded_files:
        try:
            df = parse_bank_statement(file)
            df = classify_dataframe(df)
            all_data.append(df)
        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {e}")

    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)

        st.subheader("🧾 Transactions")
        st.dataframe(combined_df)

        # 📊 Budget summary
        st.subheader("📈 Year-to-Date Summary by Category")
        summary = combined_df.groupby("Category")["Amount"].sum().reset_index()
        st.bar_chart(summary.set_index("Category"))

        # 📥 Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            combined_df.to_excel(writer, index=False, sheet_name="Transactions")
            summary.to_excel(writer, index=False, sheet_name="Summary")
        st.download_button("📥 Download Excel", output.getvalue(), "Finance_Report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Upload your FNB bank statements to begin.")