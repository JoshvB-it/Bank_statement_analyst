def classify_transactions(df):
    def classify(desc):
        desc = desc.lower()
        if "salary" in desc or "deposit" in desc:
            return "Income"
        elif "airtime" in desc:
            return "Airtime"
        elif "electricity" in desc:
            return "Electricity"
        elif "petrol" in desc or "fuel" in desc:
            return "Petrol"
        elif "rent" in desc:
            return "Rent"
        elif "wifi" in desc or "internet" in desc:
            return "WiFi"
        elif "food" in desc or "grocery" in desc:
            return "Food"
        elif "medical" in desc or "aid" in desc:
            return "Medical Aid"
        elif "insurance" in desc:
            return "Insurance"
        elif "withdrawal" in desc:
            return "Cash"
        else:
            return "Misc"

    df["Category"] = df["Description"].apply(classify)
    return df