# fnb_bank_statement_app.py

import os
import re
from datetime import datetime
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import altair as alt

DEFAULT_PASSWORD = "josuavanbuuren@gmail.com"

CATEGORY_KEYWORDS = {
    "Income": ["pwc", "krans", "stefani"],
    "Crypto Investments": ["bx90dx7yn"],
    "Retirement": ["fnb r1500", "allen gray r1500", "alan gray r1500"],
    "Tax-Free Savings": ["fnb r1000", "allen gray r1000", "alan gray r1000"],
    "Groceries": ["checkers", "woolworths", "spar", "pick n pay"],
    "Fuel": ["engen", "shell", "bp", "total", "caltex"],
    "Medical": ["dischem", "clicks", "pharmacy", "camaf"],
    "WiFi": ["vodacom", "telkom", "mtn fibre", "cool ideas"],
    "Rent": ["just property", "rental", "rent"],
    "Transfers": [],
    "Other": [],
}

def classify_transaction(description: str, amount: float) -> str:
    desc = description.lower()
    if amount < 0:
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in desc:
                    return category
                    return "Transfers"
    else:
        for category, keywords in CATEGORY_KEYWORDS.items():
            if category == "Income":
                continue
            for kw in keywords:
                if kw in desc:
                    return category
        return "Other"

def get_statement_year(path: str) -> Optional[int]:
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    for page in doc:
        text = page.get_text()
        m = re.search(r"Statement Date\s*:\s*\d{1,2} [A-Za-z]+ (\d{4})", text)
        if m:
            return int(m.group(1))
        break
    return None

def parse_transactions(path: str) -> List[Tuple[datetime, str, float]]:
    year = get_statement_year(path) or datetime.now().year
    transactions = []
    date_pattern = r"^(\d{1,2})\s+([A-Za-z]{3})(?:\s+(.+))?$"
    number_pattern = r"^(\d{1,3}(?:,\d{3})*\.\d{2})([A-Za-z]{2})?$"
    try:
        doc = fitz.open(    except Exception:
        return transactions
    for page in doc:
        lines = [line.strip() for line in page.get_text().split("\n")]
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(date_pattern, line)
            if m:
                day, mon, remainder = m.group(1), m.group(2), m.group(3)
                desc = ""
                amount = None
                search_start = i + 1
                if remainder:
                    desc = remainder.strip()
                else:
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        mnum = re.match(number_pattern, next_line)
                        if mnum:
                            amount = float(mnum.group(1).replace(",", ""))
                            if mnum.group(2) and mnum.group(2).lower().startswith("cr"):
                                amount = -amount
                            i += 1
                        else:
                            desc = next_line
                            search_start = i + 2
                if amount is None:
                    for j in range(search_start, min(search_start + 6, len(lines))):
                        cand = lines[j].strip()
                        mnum = re.match(number_pattern, cand)
                        if mnum:
                            amount = float(mnum.group(1).replace(",", ""))
                            if mnum.group(2) and mnum.group(2).lower().startswith("cr"):
                                amount = -amount
                                            if amount is not None:
                    try:
                        dt = datetime.strptime(f"{day} {mon} {year}", "%d %b %Y")
                    except Exception:
                        dt = None
                    transactions.append((dt, desc, amount))
            i += 1
    return transactions


def parse_balances(path: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract the opening and closing balances from a statement."""
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