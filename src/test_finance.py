"""Check the finance tools against hand-derived expected results in data/expected.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finance_tools as ft

exp = json.loads((ft.DATA / "expected.json").read_text())["finance"]
inv, pay = ft.load_invoices(), ft.load_payments()
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# duplicates
check("duplicates found", ft.find_duplicate_invoices(inv) == exp["duplicates"], str(ft.find_duplicate_invoices(inv)))

# unallocated payments
matches = {m["payment_id"]: m["proposed_invoice"] for m in ft.match_unallocated_payments(inv, pay)}
check("unallocated payments matched", matches == exp["unallocated_matches"], str(matches))

# aging after matching
matched_ids = {v for v in matches.values() if v}
aging = ft.aging_report(inv, ft.DEFAULT_AS_OF, exclude_ids=matched_ids)
by_cust = {}
for a in aging:
    by_cust.setdefault(a["customer"], {})[a["invoice_id"]] = a["bucket"]
check("aging buckets per customer", by_cust == exp["aging_after_matching"], json.dumps(by_cust))

# credit note candidates
cn = [i["invoice_id"] for i in inv if "credit note" in (i["notes"] or "").lower()]
check("credit note candidates", cn == exp["credit_note_needed"], str(cn))

# name resolution from meeting wording
for q, want in [("Nordlicht Logistics", "Nordlicht Logistics GmbH"), ("Tegel Robotics", "Tegel Robotics AG"),
                ("Kreuzberg Catering", "Kreuzberg Catering Co"), ("havel print works", "Havel Print Works"),
                ("Alster Medical Supplies", "Alster Medical Supplies")]:
    got = ft.resolve_customer(q, inv)
    check(f"resolve '{q}'", got == want, str(got))
check("unknown customer returns None", ft.resolve_customer("Acme Rockets", inv) is None)

# every draft needs approval, every drafted ID exists
all_ids = {i["invoice_id"] for i in inv}
for c in ["Nordlicht Logistics", "Havel Print Works", "Kreuzberg Catering", "Alster Medical Supplies", "Tegel Robotics"]:
    rep = ft.customer_report(c, inv, pay)
    for lang in ("en", "de"):
        drafts = ft.draft_messages(rep, lang)
        check(f"drafts for {c} [{lang}] need approval", drafts and all(d["approval"] == "Pending approval" for d in drafts))
        import re
        ids = set(re.findall(r"INV-\d{4}-\d{4}", " ".join(d["body"] for d in drafts)))
        check(f"drafts for {c} [{lang}] use only real invoice IDs", ids <= all_ids, str(ids - all_ids))

# Nordlicht overdue total: 6200 + 4800 + 3100
check("Nordlicht overdue total", ft.customer_report("Nordlicht Logistics", inv, pay)["overdue_total"] == 14100.0)
# Tegel: nothing overdue after payment matched
check("Tegel has nothing overdue", ft.customer_report("Tegel Robotics", inv, pay)["aging"] == [])

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
