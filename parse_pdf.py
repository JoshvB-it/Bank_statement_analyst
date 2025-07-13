import re
import pandas as pd
import pdfplumber

def parse_fnb_pdf(pdf_file):
    transactions = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            for line in lines:
                # Match date at start and amount at end, optionally with 'C' for credit
                match = re.match(r"^(\d{2}[A-Za-z]{3})\s+(.*?)(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)(C?)$", line.strip())
                if match:
                    date = match.group(1)
                    desc = match.group(2).strip()
                    amount = match.group(3).replace(",", "")
                    is_credit = match.group(4) == "C"

                    try:
                        amount = float(amount)
                        if is_credit:
                            amount = -amount
                        transactions.append([date, desc, amount])
                    except:
                        pass

    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    return df