import streamlit as st
import pandas as pd
from io import BytesIO
from parse_pdf import parse_fnb_pdf
from classify import classify_transactions

st.set_page_config(page_title="Bank Statement Analyst", layout="centered")

st.title("📄 Bank Statement Analyst")
st.markdown("Upload your **FNB PDF bank statements** to auto-classify transactions.")

uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
    return output.getvalue()

if uploaded_files:
    all_data = []
    for uploaded_file in uploaded_files:
        st.write(f"🔍 Processing: {uploaded_file.name}")
        try:
            df = parse_fnb_pdf(uploaded_file)
            if df is not None and not df.empty:
                df_classified = classify_transactions(df)
                all_data.append(df_classified)
            else:
                st.warning(f"No data found in {uploaded_file.name}")
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        st.success("✅ Parsed and classified successfully.")
        st.dataframe(final_df)

        excel_data = convert_df_to_excel(final_df)
        st.download_button(
            label="⬇️ Download Excel",
            data=excel_data,
            file_name="classified_transactions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("No transactions could be parsed from the uploaded PDFs.")