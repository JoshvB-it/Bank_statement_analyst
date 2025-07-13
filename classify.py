def classify_transactions(df):
    def classify(description):
        description_lower = description.lower()

        if "airtime" in description_lower:
            return "Airtime"
        elif "electricity" in description_lower:
            return "Electricity"
        elif "takealot" in description_lower:
            return "Online Shopping"
        elif "spar" in description_lower or "pick n pay" in description_lower or "checkers" in description_lower:
            return "Groceries"
        elif "uber" in description_lower:
            return "Transport"
        elif "fuel" in description_lower or "petrol" in description_lower or "engen" in description_lower or "shell" in description_lower:
            return "Fuel"
        elif "salary" in description_lower or "income" in description_lower:
            return "Income"
        elif "dstv" in description_lower:
            return "Subscriptions"
        elif "dischem" in description_lower or "pharmacy" in description_lower:
            return "Medical"
        elif "insurance" in description_lower:
            return "Insurance"
        elif "netflix" in description_lower or "spotify" in description_lower:
            return "Entertainment"
        elif "restaurant" in description_lower or "spur" in description_lower or "steers" in description_lower:
            return "Eating Out"
        else:
            return "Other"

    df["Category"] = df["Description"].apply(classify)
    return df