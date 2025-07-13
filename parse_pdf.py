import re
import pandas as pd
import pdfplumber

def parse_fnb_pdf(pdf_file):
    transactions = []
    buffer = None

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")

            for line in lines:
                line = line.strip()

                # If it's a valid transaction line
                match = re.match(r"^(\d{2}[A-Za-z]{3})\s+(.*?)\s+(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)(C?)$", line)
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
                else:
                    # Possibly continuation of description from previous line
                    if transactions:
                        transactions[-1][1] += " " + line

    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    return df