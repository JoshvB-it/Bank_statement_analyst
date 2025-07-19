import fitz  # PyMuPDF
import re
from datetime import datetime

def parse_bank_statement(file):
    pdf = fitz.open(stream=file.read(), filetype="pdf")
    transactions = []
    date_pattern = r"\b\d{2} [A-Za-z]{3} \d{4}\b"
    amount_pattern = r"-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"
    
    for page in pdf:
        text = page.get_text()
        lines = text.split("\n")

        for line in lines:
            date_match = re.search(date_pattern, line)
            if date_match:
                try:
                    parts = line.split()
                    date_str = f"{parts[0]} {parts[1]} {parts[2]}"
                    date_obj = datetime.strptime(date_str, "%d %b %Y").date()

                    amount_matches = re.findall(amount_pattern, line)
                    amount_str = amount_matches[-1].replace(",", "")  # get last amount
                    amount = float(amount_str)

                    description = " ".join(parts[3:-1])

                    transactions.append({
                        "Date": date_obj,
                        "Description": description.strip(),
                        "Amount": amount
                    })
                except Exception:
                    continue

    return transactions