def classify_transaction(row):
    desc = str(row['Description']).lower()

    if "salary" in desc or "netcash071" in desc or "deposit" in desc:
        return "Income"
    elif "pick n pay" in desc or "spar" in desc or "food" in desc or "woolworths" in desc or "pnp" in desc:
        return "Groceries"
    elif "engen" in desc or "fuel" in desc or "petrol" in desc or "caltex" in desc:
        return "Transport"
    elif "medical" in desc or "dischem" in desc or "pharmacy" in desc or "apteek" in desc:
        return "Medical"
    elif "insurance" in desc or "disclife" in desc or "discinsure" in desc:
        return "Insurance"
    elif "papilon huur" in desc or "rent" in desc:
        return "Rent"
    elif "netflix" in desc or "spotify" in desc or "showmax" in desc:
        return "Entertainment"
    elif "investment" in desc or "investec" in desc or "allan gray" in desc:
        return "Savings/Investments"
    elif "gymfee" in desc or "planet fitness" in desc:
        return "Fitness"
    elif "water" in desc or "electricity" in desc or "municipality" in desc:
        return "Utilities"
    elif "pa josua" in desc or "tiende" in desc:
        return "Family"
    else:
        return "Other"

def classify_dataframe(df):
    df['Category'] = df.apply(classify_transaction, axis=1)
    return df