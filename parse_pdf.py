import pdfplumber
import pandas as pd
import re

def parse_fnb_pdf(file):
    transactions = []

    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split('\n')
                for line in lines:
                    # Look for lines with a typical transaction format
                    match = re.match(r"^(\d{2}[A-Za-z]{3})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$", line)
                    if match:
                        date, description, debit, credit = match.groups()
                        amount = float(debit.replace(",", "")) if debit != "0.00" else -float(credit.replace(",", ""))
                        transactions.append({
                            "Date": date,
                            "Description": description.strip(),
                            "Amount": amount
                        })

        if transactions:
            df = pd.DataFrame(transactions)
            return df

    except Exception as e:
        print(f"Failed to parse PDF: {e}")

    return pd.DataFrame()