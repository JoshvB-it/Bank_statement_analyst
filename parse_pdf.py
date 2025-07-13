import pdfplumber
import pandas as pd

def parse_fnb_pdf(file):
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # Skip header
                    if len(row) >= 3 and all(row[:3]):
                        date, desc, amount = row[:3]
                        rows.append([date.strip(), desc.strip(), amount.strip()])

    df = pd.DataFrame(rows, columns=["Date", "Description", "Amount"])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["Amount"] = df["Amount"].str.replace("R", "", regex=False).str.replace(",", "").str.replace(" ", "")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df.dropna(subset=["Date", "Amount"], inplace=True)
    return df