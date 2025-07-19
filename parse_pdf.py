import PyPDF2
import re
import pandas as pd

def extract_transactions_from_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ''
    for page in reader.pages:
        text += page.extract_text()

    lines = text.split('\n')
    transactions = []
    for line in lines:
        match = re.match(r"(\d{2}\s\w{3})\s+(.*?)\s+(-?\d+\.\d{2})\s+(\d+\.\d{2})", line)
        if match:
            date, description, amount, balance = match.groups()
            transactions.append({
                "Date": date,
                "Description": description.strip(),
                "Amount": float(amount),
                "Balance": float(balance)
            })

    return pd.DataFrame(transactions)