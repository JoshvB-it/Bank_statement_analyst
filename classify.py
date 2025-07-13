def classify_transactions(df):
    def classify(desc):
        desc = desc.lower()
        if any(w in desc for w in ["salary", "transfer from", "income"]):
            return "Income"
        if "investment" in desc:
            return "Investment"
        if "rent" in desc:
            return "Rent"
        if any(w in desc for w in ["eng", "total", "shell", "bp"]):
            return "Fuel"
        if any(w in desc for w in ["woolworths", "pick n pay", "spar", "dischem", "checkers"]):
            return "Groceries"
        if any(w in desc for w in ["kfc", "vida", "steers", "takealot", "restaurant"]):
            return "Food"
        if "medical" in desc or "dischem" in desc:
            return "Medical"
        if any(w in desc for w in ["spotify", "apple", "netflix"]):
            return "Subscriptions"
        return "Other"

    df["Category"] = df["Description"].apply(classify)
    return df