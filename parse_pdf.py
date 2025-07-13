import pdfplumber
import pandas as pd
import re

def parse_fnb_pdf(file):
    rows = []

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Try to extract tables
            tables = page.extract_tables()
            for table in tables:
                for row in table[1:]:
                    if len(row) >= 3:
                        date, desc, amount = row[:3]
                        rows.append([date.strip(), desc.strip(), amount.strip()])

            # Fallback: extract text if no table found
            text = page.extract_text()
            if text:
                lines = text.split("\n")
                for line in lines:
                    match = re.search(r"(\d{2}[A-Za-z]{3})\s+(.+?)\s+([\d,]+\.\d{2})", line)
                    if match:
                        date, desc, amount = match.groups()
                        rows.append([date, desc.strip(), amount.replace(",", "")])

    df = pd.DataFrame(rows, columns=["Date", "Description", "Amount"])
    df["Date"] = pd.to_datetime(df["Date"], format="%d%b", errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df.dropna(subset=["Date", "Amount"], inplace=True)
    return df