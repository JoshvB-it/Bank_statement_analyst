import pytesseract
from pdf2image import convert_from_path
import re
import pandas as pd
from datetime import datetime

def parse_bank_statement(file):
    images = convert_from_path(file, dpi=300)
    all_text = ""

    for image in images:
        text = pytesseract.image_to_string(image)
        all_text += text + "\n"

    lines = all_text.split("\n")
    transactions = []

    date_pattern = re.compile(r"\b\d{2}\s+[A-Za-z]{3}\b")
    amount_pattern = re.compile(r"[-]?\d+\.\d{2}")

    for line in lines:
        if date_pattern.search(line) and amount_pattern.search(line):
            try:
                parts = line.strip().split()
                date_str = parts[0] + " " + parts[1]
                date = datetime.strptime(date_str, "%d %b").replace(year=datetime.today().year)
                amount = float(parts[-1].replace(",", ""))
                description = " ".join(parts[2:-1])
                transactions.append({
                    "Date": date.strftime("%Y-%m-%d"),
                    "Description": description,
                    "Amount": amount
                })
            except:
                continue

    return pd.DataFrame(transactions)