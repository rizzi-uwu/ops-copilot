"""Finance tools for the Ops Copilot agent.

Design rule: every number, date and invoice ID comes from this code, never from the LLM.
The LLM decides WHICH tool to call; these functions do the exact work.
"""
import csv
import difflib
import re
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_AS_OF = date(2026, 10, 14)


# ---------- loading ----------
def load_invoices(path=None):
    with open(path or DATA / "invoices.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["amount"] = float(r["amount_eur"])
        r["due"] = date.fromisoformat(r["due_date"])
        r["issued"] = date.fromisoformat(r["issue_date"])
    return rows


def load_payments(path=None):
    with open(path or DATA / "payments.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["amount"] = float(r["amount_eur"])
    return rows


# ---------- customer lookup ----------
def _norm(s):
    s = s.lower()
    s = re.sub(r"\b(gmbh|ag|ug|co|inc|ltd|kg)\b", "", s)
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def resolve_customer(name, invoices):
    """Map a name from a meeting ('Nordlicht Logistics') to the exact customer name in the data."""
    customers = sorted({r["customer"] for r in invoices})
    target = _norm(name)
    for c in customers:
        if _norm(c) == target:
            return c
    best = difflib.get_close_matches(target, [_norm(c) for c in customers], n=1, cutoff=0.75)
    if best:
        for c in customers:
            if _norm(c) == best[0]:
                return c
    return None


# ---------- tool 1: match unallocated payments ----------
def match_unallocated_payments(invoices, payments):
    """Find payments with no allocated invoice and propose a match.

    Rule 1: the reference contains an invoice ID  -> high confidence.
    Rule 2: same payer and exactly one open invoice with the same amount -> medium confidence.
    Several candidates -> 'ambiguous' (a human must decide). Nothing is changed automatically.
    """
    open_inv = [i for i in invoices if i["status"] == "open"]
    results = []
    for p in payments:
        if p["allocated_invoice"]:
            continue
        found = re.search(r"INV-\d{4}-\d{4}", p["reference"] or "")
        if found and any(i["invoice_id"] == found.group() for i in open_inv):
            results.append(dict(payment_id=p["payment_id"], payer=p["payer"], amount=p["amount"],
                                proposed_invoice=found.group(), confidence="high",
                                reason="invoice ID found in payment reference"))
            continue
        cands = [i for i in open_inv if i["customer"] == p["payer"] and abs(i["amount"] - p["amount"]) < 0.005]
        if len(cands) == 1:
            results.append(dict(payment_id=p["payment_id"], payer=p["payer"], amount=p["amount"],
                                proposed_invoice=cands[0]["invoice_id"], confidence="medium",
                                reason="same payer and exact amount, only one open invoice fits"))
        elif len(cands) > 1:
            results.append(dict(payment_id=p["payment_id"], payer=p["payer"], amount=p["amount"],
                                proposed_invoice=None, confidence="ambiguous",
                                reason=f"{len(cands)} open invoices have this amount: " + ", ".join(c["invoice_id"] for c in cands)))
        else:
            results.append(dict(payment_id=p["payment_id"], payer=p["payer"], amount=p["amount"],
                                proposed_invoice=None, confidence="none",
                                reason="no open invoice matches payer and amount"))
    return results


# ---------- tool 2: duplicates ----------
def find_duplicate_invoices(invoices):
    """Open invoices with same customer, amount, description and issue date."""
    groups = {}
    for i in invoices:
        if i["status"] != "open":
            continue
        key = (i["customer"], i["amount_eur"], i["description"], i["issue_date"])
        groups.setdefault(key, []).append(i["invoice_id"])
    return [sorted(ids) for ids in groups.values() if len(ids) > 1]


# ---------- tool 3: aging ----------
def bucket_for(days_overdue):
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    return "61+"


def aging_report(invoices, as_of=DEFAULT_AS_OF, exclude_ids=()):
    """Aging buckets for open invoices (minus ones matched to a payment)."""
    out = []
    for i in invoices:
        if i["status"] != "open" or i["invoice_id"] in exclude_ids:
            continue
        days = (as_of - i["due"]).days
        out.append(dict(invoice_id=i["invoice_id"], customer=i["customer"], amount=i["amount"],
                        due_date=i["due_date"], days_overdue=max(days, 0), bucket=bucket_for(days)))
    return out


# ---------- tool 4: customer report ----------
def customer_report(name, invoices=None, payments=None, as_of=DEFAULT_AS_OF):
    invoices = invoices or load_invoices()
    payments = payments or load_payments()
    customer = resolve_customer(name, invoices)
    if not customer:
        return dict(found=False, query=name)
    matches = [m for m in match_unallocated_payments(invoices, payments) if m["payer"] == customer]
    matched_ids = {m["proposed_invoice"] for m in matches if m["proposed_invoice"]}
    dups = [g for g in find_duplicate_invoices(invoices) if invoices_by_id(invoices)[g[0]]["customer"] == customer]
    aging = [a for a in aging_report(invoices, as_of, exclude_ids=matched_ids) if a["customer"] == customer]
    credit = [i["invoice_id"] for i in invoices
              if i["customer"] == customer and i["status"] == "open" and "credit note" in (i["notes"] or "").lower()]
    overdue_total = round(sum(a["amount"] for a in aging if a["bucket"] != "current"), 2)
    return dict(found=True, customer=customer, as_of=as_of.isoformat(), aging=aging,
                overdue_total=overdue_total, duplicates=dups, payment_matches=matches,
                credit_note_candidates=credit)


def invoices_by_id(invoices):
    return {i["invoice_id"]: i for i in invoices}


# ---------- tool 5: drafts (templates, so numbers are exact) ----------
def _eur(x, lang):
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " EUR" if lang == "de" else f"EUR {s}"


def draft_messages(report, lang="en"):
    """Create drafts for a customer report. Every draft needs human approval before sending."""
    if not report.get("found"):
        return []
    c = report["customer"]
    drafts = []
    lines = lambda items: "\n".join(
        f"  - {a['invoice_id']}: {_eur(a['amount'], lang)}, due {a['due_date']} ({a['days_overdue']} days overdue)"
        if lang == "en" else
        f"  - {a['invoice_id']}: {_eur(a['amount'], lang)}, fällig am {a['due_date']} ({a['days_overdue']} Tage überfällig)"
        for a in items)

    overdue = [a for a in report["aging"] if a["bucket"] != "current"]
    dup_ids = {i for g in report["duplicates"] for i in g}
    overdue = [a for a in overdue if a["invoice_id"] not in dup_ids]
    severe = [a for a in overdue if a["bucket"] == "61+"]

    if severe:
        total = round(sum(a["amount"] for a in overdue), 2)
        if lang == "de":
            body = (f"Betreff: Letzte Mahnung - überfällige Rechnungen\n\nSehr geehrte Damen und Herren,\n\n"
                    f"trotz früherer Erinnerungen sind folgende Rechnungen von {c} weiterhin offen:\n{lines(overdue)}\n\n"
                    f"Gesamtbetrag: {_eur(total, lang)}. Bitte überweisen Sie den Betrag innerhalb von 7 Tagen. "
                    f"Andernfalls behalten wir uns vor, das Konto zu sperren.\n\nMit freundlichen Grüßen")
        else:
            body = (f"Subject: Final notice - overdue invoices\n\nDear {c} team,\n\n"
                    f"despite earlier reminders the following invoices remain unpaid:\n{lines(overdue)}\n\n"
                    f"Total outstanding: {_eur(total, lang)}. Please pay within 7 days. "
                    f"Otherwise we reserve the right to suspend the account.\n\nKind regards")
        drafts.append(dict(kind="dunning_letter", customer=c, body=body, approval="Pending approval"))
    elif overdue:
        total = round(sum(a["amount"] for a in overdue), 2)
        if lang == "de":
            body = (f"Betreff: Zahlungserinnerung\n\nSehr geehrte Damen und Herren,\n\n"
                    f"uns liegt für folgende Rechnungen von {c} noch kein Zahlungseingang vor:\n{lines(overdue)}\n\n"
                    f"Offener Betrag: {_eur(total, lang)}. Falls Sie bereits gezahlt haben, ignorieren Sie diese Nachricht bitte.\n\nMit freundlichen Grüßen")
        else:
            body = (f"Subject: Payment reminder\n\nDear {c} team,\n\n"
                    f"we have not yet received payment for these invoices:\n{lines(overdue)}\n\n"
                    f"Outstanding: {_eur(total, lang)}. If you have already paid, please disregard this message.\n\nKind regards")
        drafts.append(dict(kind="payment_reminder", customer=c, body=body, approval="Pending approval"))

    for g in report["duplicates"]:
        keep, cancel = g[0], g[1:]
        body = (f"Credit note request (internal)\nCustomer: {c}\nPossible duplicate invoices: {', '.join(g)}\n"
                f"Proposed action: keep {keep}, issue a credit note to cancel {', '.join(cancel)}.\n"
                f"Check before approving: confirm with the customer that only one sponsor package was ordered.")
        drafts.append(dict(kind="duplicate_credit_note", customer=c, body=body, approval="Pending approval"))

    for inv_id in report["credit_note_candidates"]:
        body = (f"Credit note request (internal)\nCustomer: {c}\nInvoice: {inv_id}\n"
                f"Reason: customer reported a wrong VAT rate. Proposed action: cancel with credit note and reissue the invoice.")
        drafts.append(dict(kind="credit_note_request", customer=c, body=body, approval="Pending approval"))

    for m in report["payment_matches"]:
        if m["proposed_invoice"]:
            body = (f"Payment allocation proposal (internal)\nPayment {m['payment_id']} ({_eur(m['amount'], lang)}) from {c} "
                    f"has no allocation. Proposed: allocate to {m['proposed_invoice']} ({m['reason']}; confidence {m['confidence']}).\n"
                    f"Then stop any reminder for that invoice.")
        else:
            body = (f"Payment allocation needs a human (internal)\nPayment {m['payment_id']} from {c}: {m['reason']}.")
        drafts.append(dict(kind="payment_allocation", customer=c, body=body, approval="Pending approval"))
    return drafts
