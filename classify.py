def classify_transaction(description):
    description = description.lower()

    if "airtime" in description:
        return "Airtime"
    elif "electricity" in description:
        return "Electricity"
    elif "salary" in description:
        return "Income - Salary"
    elif "interest" in description:
        return "Income - Interest"
    elif "debit order" in description or "insurance" in description:
        return "Fixed Expenses"
    elif "grocery" in description or "food" in description:
        return "Food"
    elif "fuel" in description or "petrol" in description:
        return "Transport"
    else:
        return "Other"