import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
from typing import List, Tuple, Optional
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
PASSWORD = st.secrets["APP_PASSWORD"] if "APP_PASSWORD" in st.secrets else "testpass"

def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    doc = fitz.open(path)
    transactions = []
    for page in doc:
        text = page.get_text("text")
        lines = text.split("\n")
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    date = datetime.strptime(parts[0], "%d-%b-%y")
                    amount = float(parts[-1].replace(",", ""))
                    desc = " ".join(parts[1:-1])
                    transactions.append((date, desc, amount))
                except:
                    continue
    return transactions

def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    doc = fitz.open(path)
    opening, closing = None, None
    for page in doc:
        text = page.get_text("text")
        for line in text.split("\n"):
            if "opening balance" in line.lower():
                try:
                    opening = float(line.split()[-1].replace(",", ""))
                except:
                    pass
            elif "closing balance" in line.lower():
                try:
                    closing = float(line.split()[-1].replace(",", ""))
                except:
                    pass
        if opening is not None and closing is not None:
            break
    return opening, closing

def classify_transaction(description: str, amount: float) -> str:
    desc_lower = description.lower() if description else ""

    # Income
    if amount < 0:
        if any(keyword in desc_lower for keyword in ["pwc", "krans", "stefani"]):
            return "Income"
        else:
            return "Transfers"

    # Investment subcategories
    if "bx90dx7yn" in desc_lower:
        return "Investments - Crypto"
    if ("fnb" in desc_lower or "allan gray" in desc_lower):
        if amount == 1500:
            return "Investments - Retirement"
        elif amount == 1000:
            return "Investments - Tax-Free"

    # Debit Orders
    if any(keyword in desc_lower for keyword in [
        "scheduled payment", "magtape debit", "discinsure", "gymfee", 
        "papilon huur", "pa josua", "tiende"
    ]):
        return "Debit Orders"

    # Living Expenses
    if any(keyword in desc_lower for keyword in [
        "clicks", "fresh x", "woolworths", "engen", "netflix", "spotify", "vida", 
        "mcd", "spur", "dischem", "rain", "kfc", "parking"
    ]):
        return "Living Expenses"

    # Transfers
    if "transfer" in desc_lower or "trf" in desc_lower or "fnb app transfer from" in desc_lower:
        return "Transfers"

    return "Other"

def load_transactions_from_files(files: List) -> Tuple[pd.DataFrame, pd.DataFrame]:
    all_data = []
    balance_data = []
    for f in files:
        with open(f.name, "wb") as out:
            out.write(f.getbuffer())
        txns = parse_transactions(f.name)
        opening, closing = parse_balances(f.name)
        name = Path(f.name).stem
        for t in txns:
            category = classify_transaction(t[1], t[2])
            all_data.append((t[0], t[1], t[2], category, name))
        if opening is not None and closing is not None:
            total = sum(t[2] for t in txns)
            balance_data.append((name, opening, total, opening + total, closing))
    df = pd.DataFrame(all_data, columns=["Date", "Description", "Amount", "Category", "Statement"])
    balance_df = pd.DataFrame(balance_data, columns=["Statement", "Opening", "Tx Sum", "Calculated Close", "Actual Close"])
    return df, balance_df

def build_export_dataframe(tx_df: pd.DataFrame) -> pd.DataFrame:
    if tx_df.empty:
        return pd.DataFrame(columns=["Month-Year", "Category", "Amount", "YTD Total"])
    df = tx_df.copy()
    df["Month-Year"] = df["Date"].dt.to_period("M").astype(str)
    grouped = df.groupby(["Month-Year", "Category"])["Amount"].sum().reset_index()

    category_order = {
        "Income": 0,
        "Investments - Retirement": 1,
        "Investments - Tax-Free": 2,
        "Investments - Crypto": 3,
        "Debit Orders": 4,
        "Living Expenses": 5,
        "Transfers": 6,
        "Other": 7,
    }
    grouped["Month_Order"] = pd.to_datetime(grouped["Month-Year"] + "-01")
    grouped["Cat_Order"] = grouped["Category"].map(category_order).fillna(99)
    grouped = grouped.sort_values(["Month_Order", "Cat_Order"])
    grouped["YTD Total"] = grouped["Amount"].cumsum()
    grouped = grouped.drop(columns=["Month_Order", "Cat_Order"])
    return grouped[["Month-Year", "Category", "Amount", "YTD Total"]]

def show_dashboard(tx_df: pd.DataFrame, balance_df: pd.DataFrame) -> None:
    st.subheader("Classification Overview")
    summary = tx_df.groupby("Category")["Amount"].sum().reset_index()
    summary = summary.sort_values("Amount", ascending=False)
    st.dataframe(summary.rename(columns={"Amount": "Total (ZAR)"}))

    st.subheader("Balance Validation per Statement")
    st.dataframe(balance_df)

    st.subheader("All Transactions")
    st.dataframe(tx_df.sort_values(["Date", "Statement"]))

    st.subheader("Export")
    export_df = build_export_dataframe(tx_df)
    st.dataframe(export_df)
    st.download_button("Download monthly breakdown (CSV)", export_df.to_csv(index=False), file_name="fnb_export.csv")

def main():
    st.title("🔐 FNB Bank Statement Analyzer")
    password = st.text_input("Enter password", type="password")
    if password != PASSWORD:
        st.warning("Password incorrect.")
        return

    uploaded_files = st.file_uploader("Upload PDF bank statements", type="pdf", accept_multiple_files=True)
    if uploaded_files:
        tx_df, balance_df = load_transactions_from_files(uploaded_files)
        if not tx_df.empty:
            show_dashboard(tx_df, balance_df)
        else:
            st.warning("No valid transactions found in the uploaded files.")

if __name__ == "__main__":
    main()