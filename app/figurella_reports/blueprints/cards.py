REPORT_CARDS = [
    {"key": "agenda",                "label": "Agenda",                "icon": "bi-calendar"},
    {"key": "contracts",             "label": "Contracts",             "icon": "bi-pen"},
    {"key": "customer_acquisitions", "label": "customer acquisitions", "icon": "bi-people"},
    {"key": "ibf",                   "label": "IBF",                   "icon": "bi-percent"},   # ← add back
    {"key": "last_session",          "label": "Last Session",          "icon": "bi-calendar-check"},
    {"key": "payments_done",         "label": "Payments Done",         "icon": "bi-check-circle"},
    {"key": "payments_due",          "label": "Payments Due",          "icon": "bi-calendar-day"},
    {"key": "pip",                   "label": "PIP",                   "icon": "bi-bank"},
    {"key": "subscriptions",         "label": "Subscriptions",         "icon": "bi-calendar-event"},
]
HISTORY_FILES = {c['label']: f"history_{c['key']}.xlsx" for c in REPORT_CARDS}
