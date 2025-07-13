import streamlit as st
import pandas as pd
from classify import classify_dataframe
from config import APP_PASSWORD

st.set_page_config(page_title="Finance Dashboard", layout="centered")
st.title("🔐 Personal Finance Dashboard")

# Password protection
password = st.text_input("Enter Password", type="password")
if password != APP_PASSWORD:
    st.stop()

st.success("Access granted!")

# Upload files
uploaded_files = st.file_uploader("Upload FNB bank statements (CSV or Excel)", type=["csv", "xlsx"], accept_multiple_files=True)

if uploaded_files:
    all_data = pd.DataFrame()

    for file in uploaded_files:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        if "Date" in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])

        if "Amount" not in df.columns or "Description" not in df.columns:
            st.error(f"File {file.name} is missing required columns.")
            continue

        df = classify_dataframe(df)
        all_data = pd.concat([all_data, df], ignore_index=True)

    all_data.sort_values("Date", inplace=True)
    st.subheader("📊 Year-To-Date Summary")

    all_data['Year'] = all_data['Date'].dt.year
    summary = all_data.groupby(['Year', 'Category'])['Amount'].sum().unstack(fill_value=0)
    st.dataframe(summary)

    st.subheader("📄 All Transactions")
    st.dataframe(all_data)

    # Excel Export
    @st.cache_data
    def convert_df_to_excel(df):
        return df.to_excel(index=False, engine='openpyxl')

    st.download_button(
        label="📥 Download as Excel",
        data=convert_df_to_excel(all_data),
        file_name="classified_bank_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


