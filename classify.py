# classify.py

from config import CATEGORIES
import pandas as pd

def classify_transaction(description):
    description = description.upper()
    for category, keywords in CATEGORIES.items():
        if any(keyword in description for keyword in keywords):
            return category
    return "Unclassified"

def classify_dataframe(df):
    if "Description" not in df.columns:
        raise ValueError("Missing 'Description' column in DataFrame")
    df["Category"] = df["Description"].apply(classify_transaction)
    return df