"""Generate invented invoice and payment data for the Ops Copilot demo.

All names, amounts and dates are fictional. Planted cases (used to test the agent):
  - Nordlicht Logistics GmbH: 3 open invoices in three different aging buckets
  - Kreuzberg Catering Co: one duplicate invoice pair (0119 / 0120)
  - Tegel Robotics AG: payment with blank reference that matches open invoice 0131
  - Spree Analytics GmbH: payment with vague reference that matches open invoice 0160
  - Havel Print Works: 3 open invoices, badly overdue
  - Alster Medical Supplies: invoice with wrong VAT rate (credit note needed)
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 14)


def d(s):
    return date.fromisoformat(s)


invoices = []   # dicts
payments = []   # dicts


def add_invoice(inv_id, customer, desc, issue, due, amount, status, notes=""):
    invoices.append(dict(invoice_id=inv_id, customer=customer, description=desc,
                         issue_date=issue, due_date=due, amount_eur=f"{amount:.2f}",
                         status=status, notes=notes))


# ---- planted open invoices ----
add_invoice("INV-2026-0101", "Nordlicht Logistics GmbH", "Platform licence Q2", "2026-06-30", "2026-07-30", 6200.00, "open")
add_invoice("INV-2026-0102", "Nordlicht Logistics GmbH", "Platform licence Q3 setup", "2026-07-30", "2026-08-29", 4800.00, "open")
add_invoice("INV-2026-0103", "Nordlicht Logistics GmbH", "Onboarding services", "2026-08-25", "2026-09-24", 3100.00, "open")

add_invoice("INV-2026-0119", "Kreuzberg Catering Co", "Sponsor package Partner Summit", "2026-09-20", "2026-10-20", 3500.00, "open")
add_invoice("INV-2026-0120", "Kreuzberg Catering Co", "Sponsor package Partner Summit", "2026-09-20", "2026-10-20", 3500.00, "open")

add_invoice("INV-2026-0131", "Tegel Robotics AG", "Annual support plan", "2026-09-01", "2026-09-25", 8400.00, "open")

add_invoice("INV-2026-0140", "Havel Print Works", "Workflow licence monthly", "2026-06-10", "2026-07-10", 2750.00, "open")
add_invoice("INV-2026-0141", "Havel Print Works", "Workflow licence monthly", "2026-07-10", "2026-08-10", 2750.00, "open")
add_invoice("INV-2026-0142", "Havel Print Works", "Workflow licence monthly", "2026-08-10", "2026-09-10", 2750.00, "open")

add_invoice("INV-2026-0150", "Alster Medical Supplies", "Training workshop", "2026-09-10", "2026-10-10", 5100.00, "open",
            "Customer reported wrong VAT rate on invoice - credit note and reissue needed")

add_invoice("INV-2026-0160", "Spree Analytics GmbH", "Dashboard subscription October", "2026-09-15", "2026-10-01", 2150.00, "open")

# ---- planted payments ----
payments.append(dict(payment_id="PAY-0412", date="2026-09-30", payer="Tegel Robotics AG",
                     amount_eur="8400.00", reference="", allocated_invoice=""))
payments.append(dict(payment_id="PAY-0430", date="2026-10-06", payer="Spree Analytics GmbH",
                     amount_eur="2150.00", reference="Rechnung Okt", allocated_invoice=""))

# ---- filler paid invoices with allocated payments ----
fillers = [
    ("Brandenburg Bikes UG", "Monthly subscription"),
    ("Mitte Design Studio", "Design tool licence"),
    ("Spree Analytics GmbH", "Dashboard subscription"),
    ("Nordlicht Logistics GmbH", "Integration workshop"),
    ("Tegel Robotics AG", "Hardware integration"),
    ("Brandenburg Bikes UG", "Consulting day rate"),
]
n = 1
inv_no = 1
for i in range(18):
    cust, desc = fillers[i % len(fillers)]
    issue = d("2026-03-01") + timedelta(days=random.randint(0, 150))
    due = issue + timedelta(days=30)
    amount = round(random.choice([480, 750, 980, 1200, 1500, 1850, 2200, 2600]) + random.randint(0, 90), 2)
    inv_id = f"INV-2026-{inv_no:04d}"
    inv_no += 1
    add_invoice(inv_id, cust, desc, issue.isoformat(), due.isoformat(), amount, "paid")
    paid = due - timedelta(days=random.randint(0, 12))
    payments.append(dict(payment_id=f"PAY-{300 + n:04d}", date=paid.isoformat(), payer=cust,
                         amount_eur=f"{amount:.2f}", reference=inv_id, allocated_invoice=inv_id))
    n += 1

invoices.sort(key=lambda r: r["invoice_id"])
payments.sort(key=lambda r: r["payment_id"])

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "invoices.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(invoices[0].keys()))
    w.writeheader()
    w.writerows(invoices)
with open(OUT / "payments.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(payments[0].keys()))
    w.writeheader()
    w.writerows(payments)

# ---- hand-derived expected results (as of 2026-10-14), used to test the agent ----
expected_finance = {
    "as_of": AS_OF.isoformat(),
    "duplicates": [["INV-2026-0119", "INV-2026-0120"]],
    "unallocated_matches": {"PAY-0412": "INV-2026-0131", "PAY-0430": "INV-2026-0160"},
    "aging_after_matching": {
        "Nordlicht Logistics GmbH": {"INV-2026-0101": "61+", "INV-2026-0102": "31-60", "INV-2026-0103": "1-30"},
        "Havel Print Works": {"INV-2026-0140": "61+", "INV-2026-0141": "61+", "INV-2026-0142": "31-60"},
        "Alster Medical Supplies": {"INV-2026-0150": "1-30"},
        "Kreuzberg Catering Co": {"INV-2026-0119": "current", "INV-2026-0120": "current"},
    },
    "credit_note_needed": ["INV-2026-0150"],
}
# Hand labels for the meeting reader, written by reading the transcripts.
# deadline "any" = the transcript gives no single clear date (e.g. "this week", "before the 16th"),
# so that item is matched on owner only.
def A(owner, deadline="any"):
    return {"owner": owner, "deadline": deadline}


action_labels = {
    "meeting_01_atlas_sync": [A("Ben", "2026-10-16"), A("Chloe", "2026-10-07"), A("Anna"), A("David")],
    "meeting_02_partner_summit": [A("Elena", "2026-10-12"), A("Greta", "2026-10-09"), A("Farid", "2026-10-14"), A("Hannah")],
    "meeting_03_sprint_planning": [A("Jonas", "2026-10-14"), A("Jonas", "2026-10-15"), A("Kai", "2026-10-21")],
    "meeting_04_tegel_client_call": [A("Lena", "2026-10-15"), A("Lena"), A("Marco")],
    "meeting_05_month_end_finance": [A("Nora", "2026-10-16"), A("Omar", "2026-10-14"), A("Paul", "2026-10-20"), A("Nora")],
    # Hard set (meetings 6-10): corrections, retracted commitments, vague dates, German, mixed language, hypotheticals
    "meeting_06_messy_sync": [A("Tom", "2026-10-13"), A("Petra", "2026-10-30"), A("Mira", "2026-10-12")],
    "meeting_07_vague_dates": [A("Lukas", "2026-10-23"), A("Omid", "2026-10-15"), A("Rachel")],
    "meeting_08_deutsch": [A("Stefan", "2026-10-16"), A("Dilara", "2026-10-21"), A("Max", "2026-10-21"), A("Katja", "2026-10-15")],
    "meeting_09_denglisch": [A("Felix", "2026-10-15"), A("Aylin", "2026-10-12"), A("Pavel", "2026-10-20")],
    "meeting_10_discussion_only": [A("Sofia", "2026-10-16")],
}
meeting_meta = {
    "meeting_01_atlas_sync": {"decisions": 1, "risks": 1, "finance_customers": ["Nordlicht Logistics GmbH"]},
    "meeting_02_partner_summit": {"decisions": 1, "risks": 1, "finance_customers": ["Kreuzberg Catering Co"]},
    "meeting_03_sprint_planning": {"decisions": 1, "risks": 1, "finance_customers": []},
    "meeting_04_tegel_client_call": {"decisions": 1, "risks": 1, "finance_customers": ["Tegel Robotics AG"]},
    "meeting_05_month_end_finance": {"decisions": 1, "risks": 1, "finance_customers": ["Havel Print Works", "Alster Medical Supplies"]},
    "meeting_06_messy_sync": {"decisions": 1, "risks": 1, "finance_customers": []},
    "meeting_07_vague_dates": {"decisions": 1, "risks": 1, "finance_customers": []},
    "meeting_08_deutsch": {"decisions": 1, "risks": 1, "finance_customers": []},
    "meeting_09_denglisch": {"decisions": 1, "risks": 1, "finance_customers": []},
    "meeting_10_discussion_only": {"decisions": 0, "risks": 1, "finance_customers": []},
}
expected_meetings = {
    name: {"set": "basic" if int(name.split("_")[1]) <= 5 else "hard",
           "actions": len(labels), "action_labels": labels, **meeting_meta[name]}
    for name, labels in action_labels.items()
}
with open(OUT / "expected.json", "w", encoding="utf-8") as f:
    json.dump({"finance": expected_finance, "meetings": expected_meetings}, f, indent=2)

print(f"invoices: {len(invoices)} rows, payments: {len(payments)} rows")
