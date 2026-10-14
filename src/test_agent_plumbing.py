"""Plumbing test with a scripted stand-in for the model.

This checks that the agent code is wired correctly (extraction -> items, follow-up email,
optional finance loop, outbox, approval step) and that the helpers (scoring, email template,
validation) behave. It does NOT measure how well a real model reads meetings. For that,
run evaluate.py with a real API key.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent
import approve
import followup
import meeting_reader as mr
import scoring

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
agent.OUTBOX = tmp
approve.OUTBOX = tmp

EXTRACTION = {
    "action_items": [
        {"task": "Prepare dunning letter for Havel Print Works", "owner": "Nora", "deadline": "2026-10-16", "quote": "I'll prepare the dunning letter"},
        {"task": "Raise credit note request for Alster Medical Supplies invoice", "owner": "Omar", "deadline": "2026-10-14", "quote": "I'll raise the credit note request"},
        {"task": "Update the investor report", "owner": "Paul", "deadline": "2026-10-20", "quote": "I'll update the investor report"},
        {"task": "Review the full aging report", "owner": "Nora", "deadline": "2026-10-16", "quote": "review the full aging report"},
    ],
    "decisions": [{"decision": "Suspend Havel Print Works account if unpaid by 2026-10-30", "quote": "we suspend the Havel Print Works account"}],
    "unowned_risks": [{"risk": "Audit documentation folder incomplete, nobody owns it", "quote": "no one knows who is supposed to keep it"}],
    "finance_mentions": [{"customer": "Havel Print Works", "issue": "badly overdue, three open invoices"},
                         {"customer": "Alster Medical Supplies", "issue": "wrong VAT rate, credit note"}],
}


def tu(i, name, **inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


class StubClient:
    def __init__(self):
        self.messages = self
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        if kw.get("tool_choice", {}).get("name") == "record_meeting":
            return NS(content=[tu("x1", "record_meeting", **EXTRACTION)], stop_reason="tool_use")
        n = len(kw["messages"])
        if n == 1:
            return NS(stop_reason="tool_use", content=[
                tu("t1", "get_customer_finance_report", customer_name="Havel Print Works"),
                tu("t2", "get_customer_finance_report", customer_name="Alster Medical Supplies")])
        if n == 3:
            return NS(stop_reason="tool_use", content=[
                tu("t3", "draft_followups", customer_name="Havel Print Works", language="de"),
                tu("t4", "draft_followups", customer_name="Alster Medical Supplies", language="en")])
        return NS(stop_reason="end_turn", content=[NS(type="text", text="Drafted a dunning letter and a credit note request.")])


failures = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


TRANSCRIPT = ROOT / "data/transcripts/meeting_05_month_end_finance.txt"
count = lambda items, t: sum(i["type"] == t for i in items)

# ---- default run: meeting-to-action only, finance off ----
stub = StubClient()
res = agent.run_agent(TRANSCRIPT, client=stub)
items = res["items"]
check("outbox file written", (tmp / "meeting_05_month_end_finance.json").exists())
check("4 actions, 1 decision, 1 risk", [count(items, t) for t in ("Action item", "Decision", "Risk (no owner)")] == [4, 1, 1])
check("finance is off by default: no finance items, one model call", count(items, "Finance follow-up") == 0 and stub.calls == 1)
emails = [i for i in items if i["type"] == "Follow-up email"]
check("one follow-up email, pending approval", len(emails) == 1 and emails[0]["approval"] == "Pending approval")
body = emails[0]["draft"]
check("email subject has title and date", "Subject: Recap: Month-End Finance Sync (2026-10-12)" in body)
check("email lists action with owner and date", "- Nora: Prepare dunning letter for Havel Print Works (due 2026-10-16)" in body)
check("email has decisions and unowned risks", "Decisions" in body and "Open risks with no owner" in body and "Audit documentation folder" in body)
check("only the email awaits approval", [i["type"] for i in items if i["approval"] == "Pending approval"] == ["Follow-up email"])

# ---- finance on, German drafts ----
res = agent.run_agent(TRANSCRIPT, lang="de", client=StubClient(), finance=True)
items = res["items"]
fin = [i for i in items if i["type"] == "Finance follow-up"]
check("finance on: dunning letter in German", any("Dunning Letter" in i["task"] and "Letzte Mahnung" in i["draft"] for i in fin))
check("finance on: credit note request for Alster", any("Credit Note Request" in i["task"] and "INV-2026-0150" in i["draft"] for i in fin))
check("finance on: all finance drafts pending approval", fin and all(i["approval"] == "Pending approval" for i in fin))
check("finance on: Havel dunning total is 8.250,00 EUR", any("8.250,00 EUR" in i["draft"] for i in fin))
de_email = [i for i in items if i["type"] == "Follow-up email"][0]["draft"]
check("German email uses German text", "Zusammenfassung" in de_email and "fällig 2026-10-16" in de_email)

# ---- approval step ----
pend = approve.pending()
check("pending list = follow-up email + finance drafts", len(pend) == len(fin) + 1)
approve.set_status("meeting_05_month_end_finance", pend[0][1], "Approved")
check("approve flips status", len(approve.pending()) == len(fin))

# ---- follow-up email template ----
empty = {"decisions": [], "action_items": [{"task": "Do X", "owner": "Ann", "deadline": None, "quote": ""}], "unowned_risks": []}
mail = followup.build_followup_email("Sync", "", empty)
check("email skips empty sections and handles no deadline",
      "Decisions" not in mail and "Open risks" not in mail and "- Ann: Do X (no deadline set)" in mail and "Subject: Recap: Sync" in mail)
check("parse_header reads title and date", followup.parse_header(TRANSCRIPT.read_text()) == ("Month-End Finance Sync", "2026-10-12"))

# ---- scoring ----
L = lambda o, d="any": {"owner": o, "deadline": d}
g = lambda o, d: {"owner": o, "deadline": d}
s = scoring.score_actions([L("Nora", "2026-10-16"), L("Nora")], [g("Nora", "2026-10-15"), g("Nora", "2026-10-16")])
check("scoring: dated label matched first, 'any' label takes the other", s["matched"] == 2 and not s["missed"] and not s["extra"])
s = scoring.score_actions([L("Nora", "2026-10-16"), L("Nora")], [g("Nora (finance lead)", "2026-10-16")])
check("scoring: first-name match, one missed", s["matched"] == 1 and len(s["missed"]) == 1 and not s["extra"])
s = scoring.score_actions([L("Ben", "2026-10-16")], [g("Ben", "2026-10-17")])
check("scoring: wrong date is not a match", s["matched"] == 0 and len(s["missed"]) == 1 and len(s["extra"]) == 1)
s = scoring.score_actions([L("Nora"), L("Omar")], [g("Omar", None)])
check("scoring: 'any' label ignores deadline", s["matched"] == 1 and s["missed"] == [L("Nora")])

# ---- validation catches bad model output ----
try:
    mr.validate({"action_items": [{"task": "x", "owner": "A", "deadline": "next Friday", "quote": ""}],
                 "decisions": [], "unowned_risks": [], "finance_mentions": []})
    check("validation rejects non-ISO deadline", False)
except ValueError:
    check("validation rejects non-ISO deadline", True)

# ---- label file is consistent with the transcripts ----
import datetime

exp = json.loads((ROOT / "data/expected.json").read_text())["meetings"]
tdir = ROOT / "data/transcripts"
check("labels: transcripts and labels cover the same meetings",
      sorted(p.stem for p in tdir.glob("*.txt")) == sorted(exp))
check("labels: action counts match label lists",
      all(e["actions"] == len(e["action_labels"]) for e in exp.values()))
check("labels: 5 basic and 5 hard meetings",
      sorted(e["set"] for e in exp.values()) == ["basic"] * 5 + ["hard"] * 5)


def label_problems():
    bad = []
    for n, e in exp.items():
        text = (tdir / f"{n}.txt").read_text(encoding="utf-8")
        title, date = followup.parse_header(text)
        if not title or not date:
            bad.append(f"{n}: header missing title or date")
            continue
        meeting_day = datetime.date.fromisoformat(date)
        for lab in e["action_labels"]:
            if lab["owner"] not in text:
                bad.append(f"{n}: owner {lab['owner']} not in transcript")
            if lab["deadline"] != "any":
                try:
                    if datetime.date.fromisoformat(lab["deadline"]) < meeting_day:
                        bad.append(f"{n}: deadline {lab['deadline']} before the meeting")
                except ValueError:
                    bad.append(f"{n}: bad deadline {lab['deadline']}")
    return bad


problems = label_problems()
check("labels: headers parse, owners appear in transcripts, deadlines are valid dates after the meeting", not problems)
for p in problems:
    print("   ", p)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
