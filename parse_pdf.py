import fitz  # PyMuPDF
import pandas as pd
import re

def parse_fnb_pdf(file):
    text = ""
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()

    lines = text.split("\n")
    transactions = []
    for line in lines:
        match = re.match(r"(\d{2}\s\w{3})\s+(.*?)(\d{1,3}(?:,\d{3})*\.\d{2})\s+(CR)?", line)
        if match:
            date = match.group(1)
            description = match.group(2).strip()
            amount = float(match.group(3).replace(",", ""))
            is_credit = match.group(4) == "CR"
            amount = amount if is_credit else -amount
            transactions.append((date, description, amount))

    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    return df