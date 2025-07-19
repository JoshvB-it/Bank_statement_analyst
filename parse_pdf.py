import pdfplumber
import pandas as pd
import re

def parse_bank_statement(uploaded_file):
    transactions = []

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for line in lines:
                match = re.match(r"(\d{2}[A-Za-z]{3})\s+(.+?)\s+(-?\d+\.\d{2})\s+(-?\d+\.\d{2})", line)
                if match:
                    date, description, amount, _ = match.groups()
                    try:
                        amount = float(amount.replace(",", ""))
                        transactions.append({
                            "Date": date,
                            "Description": description.strip(),
                            "Amount": amount
                        })
                    except:
                        continue

    if transactions:
        return pd.DataFrame(transactions)
    else:
        return pd.DataFrame(columns=["Date", "Description", "Amount"])