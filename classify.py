def classify_transaction(description, amount):
    desc = description.lower()
    if "salary" in desc or "income" in desc:
        return "Income"
    elif "rent" in desc:
        return "Rent"
    elif "petrol" in desc or "fuel" in desc:
        return "Petrol"
    elif "food" in desc or "restaurant" in desc or "grocery" in desc:
        return "Food"
    elif "wifi" in desc or "internet" in desc:
        return "WiFi"
    elif "medical" in desc or "aid" in desc:
        return "Medical Aid"
    elif "insurance" in desc:
        return "Insurance"
    elif "electricity" in desc or "prepaid" in desc:
        return "Utilities"
    elif "airtime" in desc or "mobile" in desc:
        return "Phones"
    elif amount > 0:
        return "Income"
    else:
        return "Miscellaneous"