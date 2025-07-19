# parse_pdf.py

import fitz  # PyMuPDF
import pandas as pd
import re

def extract_text_from_pdf(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def parse_fnb_text_to_dataframe(text):
    lines = text.splitlines()
    transactions = []

    # Updated: Match lines with proper date + description + amount
    transaction_pattern = re.compile(r'^(\d{2} [A-Za-z]{3}) (.+?) (\d{1,3}(?:,\d{3})*(?:\.\d{2})?)(Cr)?$')

    for line in lines:
        line = line.strip()
        match = transaction_pattern.match(line)
        if match:
            date = match.group(1)
            description = match.group(2).strip()
            amount_str = match.group(3).replace(",", "")
            amount = float(amount_str)
            is_credit = match.group(4) == "Cr"
            amount = amount if not is_credit else -amount  # Flip sign if Cr
            transactions.append((date, description, -amount))  # Make expenses negative

    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    return df

def parse_bank_statement(file):
    text = extract_text_from_pdf(file)
    df = parse_fnb_text_to_dataframe(text)
    return df