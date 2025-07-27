# FINAL corrected app.py
import os
import re
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

DEFAULT_PASSWORD = "changeme"

CATEGORY_KEYWORDS = {
    "Income": ["pwc", "krans", "stefani", "salary", "bonus", "income", "deposit"],
    "Groceries": ["woolworths", "cc fresh", "fresh x", "pick n pay", "spar", "checkers", "food lovers", "pnp", "spaza", "fruit and veg"],
    "Health & Pharmacy": ["clicks", "dis-chem", "pharmacy", "chemist", "clinic"],
    "Clothing & Accessories": ["mr price", "mrp", "takkie", "tekkie", "k jewels", "jeweller", "jewellery", "sheetstreet", "sportscene", "pep home", "pep", "edgars", "sport"],
    "Food & Drink": ["bk ", "kfc", "mcd", "roco", "spur", "king pie", "mochachos", "milky lane", "salsa", "mama", "restaurant", "coffee", "diner", "pizza", "steers", "galitos", "burger", "chips"],
    "Fuel & Transport": ["engen", "sasol", "bp", "caltex", "shell", "petrol", "diesel", "parking", "uber", "bolt"],
    "Entertainment & Digital": ["spotify", "netflix", "apple.com", "microsoft", "play", "itunes", "book", "exclusive books", "gym", "movie", "cinema", "showmax", "hbomax", "disney", "amazon"],
    "Education & School": ["laerskool", "school", "tuition", "netcash", "scholar", "fees", "uniform", "books"],
    "Bank Charges & Fees": ["byc debit", "service fee", "bank charge", "interest", "facility fee", "admin fee"],
}

def get_statement_year(path: str) -> Optional[int]:
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
    year = get_statement_year(path) or datetime.now().year
    transactions = []
    date_pattern = r"^(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$"
    number_pattern = r"^(\d{1,3}(?:,\d{3})*\.\d{2})([A-Za-z]{2})?$"
    try:
        doc = fitz.open(path)
        for page in doc:
            lines = [line.strip() for line in page.get_text().split("\n")]
            i = 0
            while i < len(lines):
                line = lines[i]
                m = re.match(date_pattern, line)
                if m:
                    day, mon, remainder = m.group(1), m.group(2), m.group(3)
                    desc, amount = "", None
                    search_start = i + 1
                    if remainder:
                        desc = remainder.strip()
                    else:
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            mnum = re.match(number_pattern, next_line)
                            if mnum:
                                amount = float(mnum.group(1).replace(",", ""))
                                suffix = mnum.group(2).lower() if mnum.group(2) else ""
                                if suffix.startswith("cr"):
                                    amount = amount
                                else:
                                    amount = -amount
                                i += 1
                            else:
                                desc = next_line
                                search_start += 1
                    if amount is None:
                        for j in range(search_start, min(search_start + 6, len(lines))):
                            cand = lines[j].strip()
                            mnum = re.match(number_pattern, cand)
                            if mnum:
                                amount = float(mnum.group(1).replace(",", ""))
                                suffix = mnum.group(2).lower() if mnum.group(2) else ""
                                if suffix.startswith("cr"):
                                    amount = amount
                                else:
                                    amount = -amount
                                break
                    if amount is not None:
                        try:
                            dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                            transactions.append((dt, desc, amount))
                        except:
                            pass
                i += 1
    except Exception:
        pass
    return transactions

def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    opening = None
    closing = None
    try:
        doc = fitz.open(path)
    except Exception:
        return (opening, closing)
    pattern = re.compile(r"(Opening|Closing) Balance\s+([\d,]+\.\d{2})\s*(Cr|Dr)?", re.IGNORECASE)
    for page in doc:
        text = page.get_text()
        for match in pattern.finditer(text):
            label, num_str, suffix = match.groups()
            amount = float(num_str.replace(",", ""))
            if suffix and suffix.lower().startswith("dr"):
                amount = -amount
            if label.lower().startswith("opening"):
                opening = amount
            elif label.lower().startswith("closing"):
                closing = amount
        if opening is not None and closing is not None:
            break
    return (opening, closing)

def classify_transaction(description: str, amount: float) -> str:
    desc_lower = description.lower() if description else ""
    if amount > 0:
        for keyword in CATEGORY_KEYWORDS.get("Income", []):
            if keyword in desc_lower:
                return "Income"
        return "Transfers"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "Income":
            continue
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return "Other"

# ... rest of app can be appended below
