"""Fixed reference lists. Must match Prompts/DATA_GENERATION_PROMPT.md."""

SERVICES = {
    # service: (importance, owner team)
    "Email": ("Critical", "Applications"),
    "Company Login": ("Critical", "Service Desk"),
    "VPN": ("Critical", "Network"),
    "Finance System": ("Critical", "Applications"),
    "Payroll System": ("Critical", "Applications"),
    "Company Website": ("Critical", "Applications"),
    "Chat & Video Calls": ("Important", "Applications"),
    "Shared Files": ("Important", "Applications"),
    "Office Wi-Fi": ("Important", "Network"),
    "Laptop / Desktop": ("Minor", "Desktop Support"),
    "Printer": ("Minor", "Desktop Support"),
    "Mobile Phone": ("Minor", "Desktop Support"),
    "Software Install": ("Minor", "Desktop Support"),
    "Other / Not sure": ("Minor", "Service Desk"),
}

ENVIRONMENTS = ["Production", "Test", "Not applicable"]
WHO_AFFECTED = ["Just me", "My team", "Many teams", "Customers"]
TEAMS = ["Service Desk", "Network", "Applications", "Desktop Support", "Security"]
SYMPTOM_TYPES = ["outage", "blocked", "slow", "request", "question"]

CATEGORIES = {
    "Account & Access": ["Password reset", "Account locked", "Need access"],
    "Email & Communication": ["Email problem", "Chat or video call problem", "Calendar problem"],
    "Network": ["VPN problem", "Wi-Fi problem", "Internet slow or down"],
    "Business System": ["Error or won't open", "Slow", "Wrong data"],
    "Device & Software": ["Computer problem", "Printer problem", "Phone problem", "Install software"],
    "Security": ["Suspicious email", "Virus", "Lost or stolen device"],
}

SUBCATEGORY_TO_CATEGORY = {sub: cat for cat, subs in CATEGORIES.items() for sub in subs}
