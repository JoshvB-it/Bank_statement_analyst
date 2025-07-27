# streamlit_app.py

import re
import tempfile
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

# Debug banner
st.sidebar.markdown("**🐛 Parser version:** 2025-07-27-v3")

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
    try:
        doc = fitz.open(path)
        for page in doc:
            text = page.get_text("text")
            m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
            if m:
                return int(m.group(1))
    except Exception:
        return None
    return None


def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    doc = fitz.open(path)
    lines: List[str] = []
    for page in doc:
        lines.extend(page.get_text("text").splitlines())

    year = get_statement_year(path) or datetime.now().year
    transactions: List[Tuple[datetime, str, float]] = []

    single_re = re.compile(
        r'^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(.+?)\s+'
        r'(\d{1,3}(?:,\d{3})*\.\d{2})(Cr|Dr)?\s*$',
        re.IGNORECASE
    )
    start_re = re.compile(
        r'^\s*(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$',
        re.IGNORECASE
    )
    num_re = re.compile(r'^(\d{1,3}(?:,\d{3})*\.\d{2})(Cr|Dr)?$', re.IGNORECASE)

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i].strip()

        # 1) single-line transaction
        m1 = single_re.match(raw)
        if m1:
            day, mon, desc, num_str, drcr = m1.groups()
            amt = float(num_str.replace(",", ""))
            if not drcr or not drcr.lower().startswith("cr"):
                amt = -amt
            try:
                dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                transactions.append((dt, desc.strip(), amt))
            except ValueError:
                pass
            i += 1
            continue

        # 2) multi-line transaction
        m2 = start_re.match(raw)
        if m2:
            day, mon, rest = m2.groups()
            desc_lines: List[str] = []
            if rest:
                desc_lines.append(rest.strip())

            j = i + 1
            found = False
            while j < n:
                nxt = lines[j].strip()
                # New transaction starts when date+month pattern appears again
                if start_re.match(nxt):
                    break
                m3 = num_re.match(nxt)
                if m3:
                    num_str, drcr = m3.groups()
                    amt = float(num_str.replace(",", ""))
                    if not drcr or not drcr.lower().startswith("cr"):
                        amt = -amt
                    desc = " ".join(desc_lines).strip()
                    try:
                        dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                        transactions.append((dt, desc, amt))
                    except ValueError:
                        pass
                    found = True
                    break
                desc_lines.append(nxt)
                j += 1

            i = j + 1 if found else i + 1
            continue

        i += 1

    return transactions


def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Grabs the Opening and Closing balances by matching:
      - 'Opening balance [as at ...] R1,234.56'
      - 'Closing balance [as at ...] R1,234.56'
    """
    opening: Optional[float] = None
    closing: Optional[float] = None

    try:
        doc = fitz.open(path)
    except Exception:
        return opening, closing

    # Consolidate all text so we can match across lines
    full_text = "\n".join(page.get_text("text") for page in doc)

    # Regex covers optional "as at DD/MM/YYYY", optional colon or spaces, and optional "R" symbol
    bal_re = re.compile(
        r"(Opening|Closing)\s*balance"                              # label
        r"(?:\s*as at\s*[\d/]{1,10})?"                              # optional "as at" date
        r"[:\sRr]*"                                                 # optional separator and currency R
        r"([\d,]+\.\d{2})"                                          # amount
        r"(?:\s*(Cr|Dr))?",                                         # optional Cr/Dr
        re.IGNORECASE
    )

    for m in bal_re.finditer(full_text):
        label = m.group(1).lower()
        num_str = m.group(2)
        suffix = m.group(3)
        amt = float(num_str.replace(",", ""))
        if suffix and suffix.lower().startswith("dr"):
            amt = -amt

        if label == "opening":
            opening = amt
        elif label == "closing":
            closing = amt

    return opening, closing


def classify_transaction(description: str, amount: float) -> str:
    desc = (description or "").lower()
    if amount > 0:
        for kw in CATEGORY_KEYWORDS["Income"]:
            if kw in desc:
                return "Income"
        return "Transfers"
    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat == "Income":
            continue
        for kw in kws:
            if kw in desc:
                return cat
    return "Other" if abs(amount) <= 500 else "Uncategorized"


def main():
    st.set_page_config(page_title="FNB Statement Analyzer", layout="wide")
    st.title("📑 FNB Bank Statement Analyzer")

    pwd = st.sidebar.text_input("Password", type="password")
    if pwd != DEFAULT_PASSWORD:
        st.sidebar.warning("Enter the password to proceed")
        st.stop()

    uploaded = st.file_uploader(
        "Upload FNB bank statement PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )
    if not uploaded:
        st.info("Please upload one or more PDF bank statements to continue.")
        return

    balance_rows = []
    all_txns: List[Tuple[datetime, str, float, str]] = []

    for file in uploaded:
        # write to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        opening, closing = parse_balances(tmp_path)
        txns = parse_transactions(tmp_path)

        # Debug: show count per file
        st.sidebar.write(f"{file.name}: parsed {len(txns)} transactions")
        st.sidebar.write(f"{file.name}: opening={opening}, closing={closing}")

        expected = None
        if opening is not None:
            expected = opening + sum(amt for _, _, amt in txns)

        balance_rows.append({
            "Statement": file.name,
            "Opening": opening,
            "Expected Closing": expected,
            "Actual Closing": closing,
            "Difference": (closing - expected) if (closing is not None and expected is not None) else None
        })

        for dt, desc, amt in txns:
            all_txns.append((dt, desc, amt, file.name))

    # Balance check table
    st.subheader("Balance Check per Statement")
    df_bal = pd.DataFrame(balance_rows)
    st.dataframe(
        df_bal[["Statement", "Opening", "Expected Closing", "Actual Closing", "Difference"]],
        use_container_width=True
    )

    # Transactions & categorization
    df_tx = pd.DataFrame(all_txns, columns=["Date", "Description", "Amount", "Source"])
    df_tx["Category"] = df_tx.apply(
        lambda r: classify_transaction(r.Description, r.Amount), axis=1
    )

    # Summary
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

    # Bar chart
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