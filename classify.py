import pandas as pd

def classify_transaction(row):
    desc = str(row['Description']).lower()

    if "salary" in desc or "deposit" in desc:
        return "Income"
    elif "pick n pay" in desc or "food" in desc:
        return "Groceries"
    elif "engen" in desc or "petrol" in desc:
        return "Transport"
    elif "medical" in desc:
        return "Medical"
    elif "insurance" in desc:
        return "Insurance"
    elif "rent" in desc:
        return "Rent"
    else:
        return "Other"

def classify_dataframe(df):
    df['Category'] = df.apply(classify_transaction, axis=1)
    return df