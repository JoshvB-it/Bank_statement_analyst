# streamlit_app.py

import os
import re
import tempfile
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

DEFAULT_PASSWORD = "changeme"

CATEGORY_KEYWORDS = {
    "Income": ["pwc", "krans", "stefani", "salary", "bonus", "income", "deposit"],
    "Groceries": [
        "woolworths", "cc fresh", "fresh x", "pick n pay", "spar",
        "checkers", "food lovers", "pnp", "spaza", "fruit and veg"
    ],
    "Health & Pharmacy": ["clicks", "dis-chem", "pharmacy", "chemist", "clinic"],
    "Clothing & Accessories": [
        "mr price", "mrp", "takkie", "tekkie", "k jewels", "jeweller",
        "jewellery", "sheetstreet", "sportscene", "pep home", "pep",
        "edgars", "sport"
    ],
    "Food & Drink": [
        "bk ", "kfc", "mcd", "roco", "spur", "king pie", "mochachos",
        "milky lane", "salsa", "mama", "restaurant", "coffee", "diner",
        "pizza", "steers", "galitos", "burger", "chips"
    ],
    "Fuel & Transport": [
        "engen", "sasol", "bp", "caltex", "shell", "petrol", "diesel",
        "parking", "uber", "bolt"
    ],
    "Entertainment & Digital": [
        "spotify", "netflix", "apple.com", "microsoft", "play", "itunes",
        "book", "exclusive books", "gym", "movie", "cinema", "showmax",
        "hbomax", "disney", "amazon"
    ],
    "Education & School": [
        "laerskool", "school", "tuition", "netcash", "scholar", "fees",
        "uniform", "books"
    ],
    "Bank Charges & Fees": [
        "byc debit", "service fee", "bank charge", "interest",
        "facility fee", "admin fee"
    ],
}


def get_statement_year(path: str) -> Optional[int]:
    """
    Reads the first page looking for 'Statement Date : DD MMM YYYY' to extract year.
    """
    try:
        doc = fitz.open(path)
        for page in doc:
            text = page.get_text()
            m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
            if m:
                return int(m.group(1))
            break
    except Exception:
        return None
    return None


def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    """
    Token-based parsing: splits each line into words, finds the first
    numeric token (the transaction amount), and treats everything before
    it (after date & month) as the description.
    """
    transactions: List[Tuple[datetime, str, float]] = []
    year = get_statement_year(path) or datetime.now().year

    # pattern for amounts like '1,234.56', with optional 'Cr'/'Dr'
    number_re = re.compile(r"^(\d{1,3}(?:,\d{3})*\.\d{2})(Cr|Dr)?$", re.IGNORECASE)

    try:
        doc = fitz.open(path)
        for page in doc:
            for raw in page.get_text("text").splitlines():
                parts = raw.strip().split()
                if len(parts) < 4:
                    continue

                day, mon = parts[0], parts[1]
                if not day.isdigit() or not re.match(r"^[A-Za-z]{3}$", mon):
                    continue

                # collect description tokens until we hit the first amount token
                desc_tokens = []
                amount = None

                for token in parts[2:]:
                    m = number_re.match(token)
                    if m:
                        num_str, drcr = m.groups()
                        amt = float(num_str.replace(",", ""))
                        # if no 'Cr', treat as debit
                        if not drcr or not drcr.lower().startswith("cr"):
                            amt = -amt
                        amount = amt
                        break
                    else:
                        desc_tokens.append(token)

                if amount is None:
                    continue  # no valid amount on this line

                desc = " ".join(desc_tokens)
                try:
                    dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                except ValueError:
                    continue

                transactions.append((dt, desc, amount))

    except Exception:
        pass  # skip files that won't open

    return transactions


def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Finds 'Opening Balance X,XXX.XX Cr/Dr' and 'Closing Balance ...'
    """
    opening: Optional[float] = None
    closing: Optional[float] = None

    try:
        doc = fitz.open(path)
    except Exception:
        return opening, closing

    pattern = re.compile(
        r"(Opening|Closing) Balance\s+([\d,]+\.\d{2})\s*(Cr|Dr)?",
        re.IGNORECASE
    )
    for page in doc:
        text = page.get_text()
        for match in pattern.finditer(text):
            label, num_str, suffix = match.groups()
            amt = float(num_str.replace(",", ""))
            if suffix and suffix.lower().startswith("dr"):
                amt = -amt
            if label.lower().startswith("opening"):
                opening = amt
            else:
                closing = amt
        if opening is not None and closing is not None:
            break

    return opening, closing


def classify_transaction(description: str, amount: float) -> str:
    desc = (description or "").lower()

    # income vs transfers
    if amount > 0:
        for kw in CATEGORY_KEYWORDS["Income"]:
            if kw in desc:
                return "Income"
        return "Transfers"

    # match expense categories
    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat == "Income":
            continue
        for kw in kws:
            if kw in desc:
                return cat

    # fallback: small debits → Other; large debits → Uncategorized
    if abs(amount) <= 500:
        return "Other"
    return "Uncategorized"


def main():
    st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
    st.title("📑 FNB Bank Statement Analyzer")

    pwd = st.sidebar.text_input("Password", type="password")
    if pwd != DEFAULT_PASSWORD:
        st.sidebar.warning("Enter the password to proceed")
        st.stop()

    uploaded = st.file_uploader(
        "Upload your FNB bank statement PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )
    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_data = []
    all_transactions = []

    for file in uploaded:
        # write to temp file for PyMuPDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        opening, closing = parse_balances(tmp_path)
        txns = parse_transactions(tmp_path)

        expected = None
        if opening is not None:
            expected = opening + sum(amt for _, _, amt in txns)

        balance_data.append({
            "Statement": file.name,
            "Opening": opening,
            "Expected Closing": expected,
            "Actual Closing": closing,
            "Difference": (closing - expected) if (closing is not None and expected is not None) else None
        })

        for dt, desc, amt in txns:
            all_transactions.append((dt, desc, amt, file.name))

    # --- Balance check ---
    st.subheader("Balance Check per Statement")
    df_bal = pd.DataFrame(balance_data)
    st.dataframe(
        df_bal[["Statement", "Opening", "Expected Closing", "Actual Closing", "Difference"]],
        use_container_width=True
    )

    # --- Transactions & categories ---
    df_tx = pd.DataFrame(
        all_transactions,
        columns=["Date", "Description", "Amount", "Source"]
    )
    df_tx["Category"] = df_tx.apply(
        lambda r: classify_transaction(r.Description, r.Amount),
        axis=1
    )

    # --- Summary ---
    st.subheader("Summary of Spending and Income")
    summary = (
        df_tx.groupby("Category")["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "Total (ZAR)"})
        .sort_values("Total (ZAR)", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(summary, use_container_width=True)

    # --- Bar chart ---
    st.subheader("Spending by Category")
    chart = (
        alt.Chart(summary)
        .mark_bar()
        .encode(
            x=alt.X("Total (ZAR)", title="Amount (ZAR)"),
            y=alt.Y("Category", sort="-x"),
        )
        .properties(height=400)
    )
    st.altair_chart(chart, use_container_width=True)


if __name__ == "__main__":
    main()