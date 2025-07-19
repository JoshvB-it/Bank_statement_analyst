import pdfplumber
import re
import pandas as pd

def parse_bank_statement(file):
    transactions = []

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            lines = text.split('\n')

            for line in lines:
                match = re.match(r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)$", line)
                if match:
                    date, description, amount = match.groups()
                    amount = float(amount.replace(",", ""))
                    transactions.append({
                        "Date": pd.to_datetime(date, format="%d/%m/%Y"),
                        "Description": description.strip(),
                        "Amount": amount
                    })

    return pd.DataFrame(transactions)