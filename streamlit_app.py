import streamlit as st
import pandas as pd
from io import BytesIO
from parse_pdf import parse_fnb_pdf
from classify import classify_transaction

# --- PASSWORD PROTECTION ---
PASSWORD = "Poen@enMilo131!"
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    password = st.text_input("Enter password to continue", type="password")
    if password == PASSWORD:
        st.session_state["authenticated"] = True
        st.experimental_rerun()
    else:
        st.stop()

# --- STREAMLIT UI ---
st.title("📄 Bank Statement Analyst")
st.caption("Upload your FNB PDF bank statements for auto-classification.")

uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

# --- PROCESS FILES ---
all_data = pd.DataFrame()

if uploaded_files:
    for file in uploaded_files:
        df = parse_fnb_pdf(file)
        df["Category"] = df["Description"].apply(classify_transaction)
        all_data = pd.concat([all_data, df], ignore_index=True)

    if not all_data.empty:
        st.success("✅ Parsed and classified successfully.")
        st.dataframe(all_data)

        # --- EXCEL EXPORT ---
        def convert_df_to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name="Transactions")
            return output.getvalue()

        excel_data = convert_df_to_excel(all_data)
        st.download_button("📥 Download Excel", data=excel_data, file_name="classified_transactions.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.error("No transactions parsed. Please check the PDF format.")