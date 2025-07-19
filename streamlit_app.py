import streamlit as st
import pandas as pd
from io import BytesIO
from parse_pdf import parse_fnb_pdf
from classify import classify_df
from config import PASSWORD, BUDGET

# Password Gate
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("Enter password", type="password")
    if password == PASSWORD:
        st.session_state.authenticated = True
        st.experimental_rerun()
    else:
        st.stop()

# Streamlit UI
st.title("🔒 FNB Statement Analyzer")

uploaded_files = st.file_uploader("📤 Upload your FNB bank statements (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for file in uploaded_files:
        df = parse_fnb_pdf(file)
        df = classify_df(df)
        all_data.append(df)

    if all_data:
        df_all = pd.concat(all_data, ignore_index=True)
        df_all["Date"] = pd.to_datetime(df_all["Date"] + " 2024", format="%d %b %Y", errors="coerce")
        df_all.dropna(subset=["Date"], inplace=True)

        ytd_summary = df_all.groupby("Category")["Amount"].sum().reset_index()

        st.subheader("📅 Year-to-Date Summary")
        st.dataframe(ytd_summary)

        st.subheader("📊 Budget Comparison")
        budget_df = pd.DataFrame(BUDGET.items(), columns=["Category", "Budget"])
        comparison = pd.merge(budget_df, ytd_summary, on="Category", how="left").fillna(0)
        comparison["Variance"] = comparison["Budget"] - comparison["Amount"]
        st.dataframe(comparison)

        st.bar_chart(comparison.set_index("Category")[["Amount", "Budget"]])

        st.subheader("📥 Download Transactions")
        def convert_df(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()

        st.download_button("Download Excel", data=convert_df(df_all), file_name="transactions.xlsx")

    else:
        st.error("❌ No data parsed from PDFs.")