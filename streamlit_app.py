import streamlit as st
import pandas as pd
import pdfplumber
import io
from datetime import datetime

# --- PDF PARSER ---
def parse_fnb_pdf(file):
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # Skip header
                    if len(row) >= 3:
                        date, desc, amount = row[:3]
                        rows.append([date, desc.strip(), amount.replace(",", "")])

    df = pd.DataFrame(rows, columns=["Date", "Description", "Amount"])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df.dropna(subset=["Date", "Amount"], inplace=True)
    return df


# --- CLASSIFICATION ---
def classify_transaction(desc):
    desc = desc.lower()
    if "salary" in desc or "income" in desc:
        return "Income"
    elif "rent" in desc:
        return "Rent"
    elif "fuel" in desc or "garage" in desc:
        return "Petrol"
    elif "food" in desc or "shoprite" in desc or "pick n pay" in desc:
        return "Groceries"
    elif "woolworths" in desc:
        return "Food & Retail"
    elif "medical" in desc or "medscheme" in desc:
        return "Medical"
    elif "insurance" in desc or "discovery" in desc:
        return "Insurance"
    elif "wifi" in desc or "telkom" in desc or "vodacom" in desc or "cell" in desc:
        return "Wi-Fi/Phones"
    elif "electricity" in desc or "utility" in desc or "municipal" in desc:
        return "Utilities"
    elif "gym" in desc:
        return "Health"
    elif "out" in desc or "restaurant" in desc or "steers" in desc:
        return "Eating Out"
    else:
        return "Other"


# --- EXPORT TO EXCEL ---
@st.cache_data
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Bank Statement")
    processed_data = output.getvalue()
    return processed_data


# --- STREAMLIT UI ---
st.set_page_config(page_title="Bank Statement Analyzer", layout="wide")
st.title("📄 FNB Bank Statement Analyzer")

uploaded_files = st.file_uploader("Upload FNB PDF bank statements", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = pd.DataFrame()

    for file in uploaded_files:
        df = parse_fnb_pdf(file)
        df["Category"] = df["Description"].apply(classify_transaction)
        all_data = pd.concat([all_data, df], ignore_index=True)

    if not all_data.empty:
        st.success(f"Processed {len(all_data)} transactions from {len(uploaded_files)} PDFs.")
        st.dataframe(all_data)

        excel_data = convert_df_to_excel(all_data)
        st.download_button(
            label="📥 Download Excel",
            data=excel_data,
            file_name="bank_statement_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data extracted from the uploaded PDFs.")