"""Follow-up email draft built from the extracted meeting items.

Built from a template, not written by the model, so it can only contain what was extracted
(and each extracted item already carries a supporting quote for the human to check).
"""
import re

COPY = {
    "en": dict(
        subject="Subject: Recap: {head}",
        hello="Hi all,",
        intro="thanks for the meeting. Here is a short recap.",
        decisions="Decisions",
        actions="Action items",
        risks="Open risks with no owner (please volunteer or assign someone)",
        no_deadline="no deadline set",
        due="due {d}",
        closing="Please reply if anything is wrong or missing.",
        regards="Best regards",
    ),
    "de": dict(
        subject="Betreff: Zusammenfassung: {head}",
        hello="Hallo zusammen,",
        intro="danke für das Meeting. Hier ist eine kurze Zusammenfassung.",
        decisions="Entscheidungen",
        actions="Aufgaben",
        risks="Offene Risiken ohne Verantwortliche (bitte übernehmen oder zuweisen)",
        no_deadline="keine Frist",
        due="fällig {d}",
        closing="Bitte antwortet, falls etwas falsch ist oder fehlt.",
        regards="Viele Grüße",
    ),
}


def parse_header(text):
    """Read 'Meeting:' and 'Date:' from the first lines of a transcript."""
    title = date = ""
    for line in text.splitlines()[:6]:
        if line.startswith("Meeting:"):
            title = line.split(":", 1)[1].strip()
        m = re.match(r"Date:\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            date = m.group(1)
    return title, date


def build_followup_email(title, date, extracted, lang="en"):
    c = COPY[lang]
    head = f"{title} ({date})" if date else title
    out = [c["subject"].format(head=head), "", c["hello"], "", c["intro"], ""]

    if extracted["decisions"]:
        out.append(c["decisions"])
        out += [f"- {d['decision']}" for d in extracted["decisions"]]
        out.append("")

    if extracted["action_items"]:
        out.append(c["actions"])
        for a in extracted["action_items"]:
            when = c["due"].format(d=a["deadline"]) if a.get("deadline") else c["no_deadline"]
            out.append(f"- {a['owner']}: {a['task']} ({when})")
        out.append("")

    if extracted["unowned_risks"]:
        out.append(c["risks"])
        out += [f"- {r['risk']}" for r in extracted["unowned_risks"]]
        out.append("")

    out += [c["closing"], "", c["regards"]]
    return "\n".join(out)
