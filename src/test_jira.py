"""Offline checks for the Jira payload builder (nothing is sent to Jira)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jira_push as j

fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


act = {"type": "Action item", "task": "Update the investor report", "owner": "Paul",
       "deadline": "2026-10-20", "approval": "Not needed", "draft": ""}
p = j.build_payload(act, "Month-End Finance Sync", "OPS")["fields"]
check("project, type and summary", p["project"] == {"key": "OPS"} and p["issuetype"] == {"name": "Task"}
      and p["summary"] == "Paul: Update the investor report")
check("due date sent", p["duedate"] == "2026-10-20")
check("labels have no spaces", p["labels"] == ["type-action-item", "meeting-month-end-finance-sync"])
check("description is ADF with owner and meeting", p["description"]["type"] == "doc"
      and any("Owner: Paul" in str(c) for c in p["description"]["content"]))

risk = {"type": "Risk (no owner)", "task": "Audit folder incomplete", "owner": "(no owner)",
        "deadline": None, "approval": "Not needed", "draft": ""}
p = j.build_payload(risk, "Sync", "OPS", "Bug")["fields"]
check("no owner prefix, no due date, custom issue type", p["summary"] == "Audit folder incomplete"
      and "duedate" not in p and p["issuetype"] == {"name": "Bug"})

mail = {"type": "Follow-up email", "task": "Follow-up email - Sync", "owner": "", "deadline": None,
        "approval": "Pending approval", "draft": "Subject: Recap\n\nHi all"}
p = j.build_payload(mail, "Sync", "OPS")["fields"]
check("email draft lands in the description", "Subject: Recap" in str(p["description"]) and p["summary"] == "Follow-up email - Sync")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
