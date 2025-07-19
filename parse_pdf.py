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

    pattern = re.compile(r"^\d{2} [A-Z][a-z]{2} \d{2} ")

    for line in lines:
        if pattern.match(line):
            parts = line.strip().split()
            if len(parts) >= 5:
                date = " ".join(parts[:3])
                amount_str = parts[-1].replace(",", "")
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                description = " ".join(parts[3:-1])
                transactions.append((date, description, amount))

    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    return df

def parse_bank_statement(file):
    text = extract_text_from_pdf(file)
    df = parse_fnb_text_to_dataframe(text)
    return df