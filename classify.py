import pdfplumber
import pandas as pd
import re

# --- Step 1: Extract and clean data from FNB PDF bank statements ---
def parse_fnb_pdf(file):
    rows = []

    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table[1:]:
                        if len(row) >= 3:
                            date = row[0].strip()
                            description = row[1].strip()
                            amount = row[2].replace(",", "").replace(" ", "")
                            rows.append([date, description, amount])
    except Exception as e:
        print(f"[ERROR] Failed to parse {file.name}: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["Date", "Description", "Amount"])

    # Clean and convert
    df["Date"] = pd.to_datetime(df["Date"], format="%d %b %Y", errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    df.dropna(subset=["Date", "Amount"], inplace=True)

    # Add placeholder for classification
    df["Category"] = df["Description"].apply(classify_transaction)
    return df


# --- Step 2: Classify transactions into income and expense categories ---
def classify_transaction(description):
    description = description.lower()

    income_keywords = ["salary", "deposit", "interest", "transfer from", "payment received"]
    food_keywords = ["pick n pay", "checkers", "spar", "woolworths", "food", "takealot"]
    petrol_keywords = ["engine", "shell", "caltex", "total", "bp"]
    airtime_keywords = ["airtime", "vodacom", "telkom", "cell c", "mtn"]
    rent_keywords = ["rent", "lease"]
    medical_keywords = ["mediclinic", "dischem", "pharmacy", "hospital", "doctor"]
    insurance_keywords = ["insurance", "sanlam", "out", "fnb life", "momentum", "discovery"]
    entertainment_keywords = ["netflix", "spotify", "showmax", "movies"]
    utilities_keywords = ["water", "electricity", "municipality", "city of", "prepaid"]
    bank_fees_keywords = ["fee", "bank charge"]

    if any(word in description for word in income_keywords):
        return "Income"
    elif any(word in description for word in food_keywords):
        return "Groceries"
    elif any(word in description for word in petrol_keywords):
        return "Petrol"
    elif any(word in description for word in airtime_keywords):
        return "Airtime"
    elif any(word in description for word in rent_keywords):
        return "Rent"
    elif any(word in description for word in medical_keywords):
        return "Medical"
    elif any(word in description for word in insurance_keywords):
        return "Insurance"
    elif any(word in description for word in entertainment_keywords):
        return "Entertainment"
    elif any(word in description for word in utilities_keywords):
        return "Utilities"
    elif any(word in description for word in bank_fees_keywords):
        return "Bank Charges"
    else:
        return "Other"