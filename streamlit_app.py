import streamlit as st
import pandas as pd
from io import BytesIO
from parse_pdf import parse_fnb_pdf
from classify import classify_transactions

st.set_page_config(page_title="Bank Statement Classifier", layout="centered")

st.title("📄 FNB Bank Statement Analyzer")
st.write("Upload your **FNB bank statements (PDFs)** and get auto-classified income and expenses.")

uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Classified")
        writer.save()
    return output.getvalue()

if uploaded_files:
    all_data = pd.DataFrame()
    for file in uploaded_files:
        df = parse_fnb_pdf(file)
        df = classify_transactions(df)
        all_data = pd.concat([all_data, df], ignore_index=True)

    if not all_data.empty:
        st.success("✅ Parsed and classified successfully.")
        st.dataframe(all_data)

        excel_data = convert_df_to_excel(all_data)
        st.download_button("📥 Download Excel", excel_data, file_name="classified_fnb.xlsx")
    else:
        st.error("No transactions detected. Check if the PDFs are FNB format.")