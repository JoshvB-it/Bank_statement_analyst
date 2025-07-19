def classify_transaction(description: str) -> str:
    description = description.lower()

    if "airtime" in description:
        return "Airtime"
    elif "electricity" in description:
        return "Electricity"
    elif "checkers" in description or "woolworths" in description or "pick n pay" in description:
        return "Groceries"
    elif "uber" in description or "bolt" in description:
        return "Transport"
    elif "salary" in description or "payment from" in description:
        return "Income"
    elif "fuel" in description or "garage" in description or "petrol" in description:
        return "Fuel"
    elif "insurance" in description:
        return "Insurance"
    elif "medical" in description or "hospital" in description:
        return "Medical"
    elif "rent" in description or "accommodation" in description:
        return "Rent"
    elif "gym" in description:
        return "Fitness"
    elif "dstv" in description or "netflix" in description or "showmax" in description:
        return "Entertainment"
    elif "takealot" in description or "shopping" in description:
        return "Online Shopping"
    else:
        return "Other"