def classify_transaction(description):
    desc = description.lower()
    if "salary" in desc or "deposit" in desc:
        return "Income"
    if "rent" in desc:
        return "Rent"
    if "checkers" in desc or "woolworths" in desc or "food" in desc:
        return "Food"
    if "petrol" in desc or "garage" in desc:
        return "Petrol"
    if "wifi" in desc or "internet" in desc:
        return "WiFi"
    if "medical" in desc or "hospital" in desc:
        return "Medical Aid"
    if "insurance" in desc:
        return "Insurance"
    if "electricity" in desc or "prepaid" in desc:
        return "Utilities"
    if "airtime" in desc or "cell" in desc:
        return "Phones"
    return "Other"