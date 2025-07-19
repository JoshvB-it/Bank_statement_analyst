import pandas as pd

def classify_transaction(description):
    desc = description.lower()

    if "airtime" in desc:
        return "Phones"
    elif "electricity" in desc:
        return "Utilities"
    elif "petrol" in desc or "fuel" in desc:
        return "Petrol"
    elif "spar" in desc or "checkers" in desc or "food" in desc:
        return "Food"
    elif "rent" in desc:
        return "Rent"
    elif "salary" in desc or "income" in desc:
        return "Income"
    elif "insurance" in desc:
        return "Insurance"
    elif "medical" in desc or "aid" in desc:
        return "Medical Aid"
    elif "wifi" in desc or "telkom" in desc:
        return "Wi-Fi"
    else:
        return "Miscellaneous"

def classify_df(df):
    df["Category"] = df["Description"].apply(classify_transaction)
    return df