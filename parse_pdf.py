import fitz  # PyMuPDF
import re
from datetime import datetime

def parse_bank_statement(file):
    pdf = fitz.open(stream=file.read(), filetype="pdf")
    transactions = []

    for page in pdf:
        text = page.get_text()
        lines = text.split("\n")

        for line in lines:
            # Match FNB date format like 01 Dec 2024
            match = re.match(r"(\d{2} [A-Za-z]{3} \d{4}) (.+) (-?\d{1,3}(?:,\d{3})*(?:\.\d{2}))", line)
            if match:
                try:
                    date_str = match.group(1)
                    description = match.group(2).strip()
                    amount_str = match.group(3).replace(",", "")
                    date_obj = datetime.strptime(date_str, "%d %b %Y").date()
                    amount = float(amount_str)

                    transactions.append({
                        "Date": date_obj,
                        "Description": description,
                        "Amount": amount
                    })
                except Exception as e:
                    continue

    return transactions