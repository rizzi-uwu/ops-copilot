"""Score extracted action items against hand-written labels.

A label is {"owner": "Ben", "deadline": "2026-10-16"}. Use deadline "any" when the transcript
does not give one clear date (for example "this week"), so the item is matched on owner only.
An extracted item matches a label when the owner's first name agrees and, if the label has a
date, the deadline agrees. Each extracted item can match only one label.
Labels with a specific date are matched first, so "any" labels cannot steal their match.
"""


def _first_name(s):
    parts = (s or "").strip().lower().split()
    return parts[0] if parts else ""


def score_actions(expected, got):
    order = sorted(range(len(expected)), key=lambda i: expected[i]["deadline"] == "any")
    used, matched, missed = set(), 0, []
    for i in order:
        e = expected[i]
        hit = None
        for j, g in enumerate(got):
            if j in used:
                continue
            if _first_name(g.get("owner")) != _first_name(e["owner"]):
                continue
            if e["deadline"] != "any" and g.get("deadline") != e["deadline"]:
                continue
            hit = j
            break
        if hit is None:
            missed.append(e)
        else:
            used.add(hit)
            matched += 1
    extra = [g for j, g in enumerate(got) if j not in used]
    return dict(matched=matched, expected=len(expected), extracted=len(got), missed=missed, extra=extra)
