"""Push an outbox file to Jira Cloud as issues (one issue per item).

Setup (once):
  1. id.atlassian.com/manage-profile/security/api-tokens -> create an API token.
  2. export JIRA_BASE_URL=https://<your-site>.atlassian.net
     export JIRA_EMAIL=<the email of your Atlassian account>
     export JIRA_API_TOKEN=<the token>
     export JIRA_PROJECT_KEY=<project key, e.g. OPS>
     optional: export JIRA_ISSUE_TYPE=Task      (default Task; must exist in the project)

Usage:
  python src/jira_push.py outbox/meeting_05_month_end_finance.json
  python src/jira_push.py outbox/meeting_05_month_end_finance.json --dry-run   (prints, sends nothing)

Notes:
  - The owner is written into the summary and description, not the Assignee field, because Jira
    assigns by account id and the meeting only gives a first name.
  - Labels carry the item type and meeting (e.g. type-action-item, meeting-month-end-finance-sync).
  - Due date is sent when there is a deadline. If the project does not show the Due date field,
    Jira rejects it and the issue is created again without it.
"""
import base64
import json
import os
import re
import sys
from pathlib import Path


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60]


def _para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}] if text else []}


def _adf(lines):
    """Minimal Atlassian Document Format: one paragraph per line."""
    return {"type": "doc", "version": 1, "content": [_para(t) for t in lines if t is not None]}


def build_payload(item, meeting, project_key, issue_type="Task"):
    owner = item.get("owner") or ""
    summary = item["task"] if not owner or owner.startswith("(") else f"{owner}: {item['task']}"
    lines = [
        f"Type: {item['type']}",
        f"Owner: {owner or 'not set'}",
        f"Source meeting: {meeting}",
        f"Approval: {item.get('approval', '')}",
    ]
    if item.get("deadline"):
        lines.append(f"Deadline: {item['deadline']}")
    if item.get("draft"):
        lines += ["", "Draft:"] + item["draft"].split("\n")
    fields = {
        "project": {"key": project_key},
        "summary": summary[:250],
        "issuetype": {"name": issue_type},
        "description": _adf(lines),
        "labels": [l for l in (f"type-{_slug(item['type'])}", f"meeting-{_slug(meeting)}") if l.strip("-")],
    }
    if item.get("deadline"):
        fields["duedate"] = item["deadline"]
    return {"fields": fields}


def push(outbox_file, dry_run=False):
    data = json.loads(Path(outbox_file).read_text(encoding="utf-8"))
    project = os.environ.get("JIRA_PROJECT_KEY") or "OPS"
    itype = os.environ.get("JIRA_ISSUE_TYPE") or "Task"
    payloads = [build_payload(i, data["meeting"], project, itype) for i in data["items"]]
    if dry_run:
        for p in payloads:
            print(json.dumps(p, indent=2, ensure_ascii=False))
        print(f"\n{len(payloads)} issue(s) would be created in project {project}. Nothing was sent.")
        return
    import requests
    base = os.environ["JIRA_BASE_URL"].rstrip("/")
    auth = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json", "Accept": "application/json"}
    for p in payloads:
        r = requests.post(f"{base}/rest/api/3/issue", headers=headers, json=p, timeout=30)
        if r.status_code == 400 and "duedate" in r.text and "duedate" in p["fields"]:
            del p["fields"]["duedate"]
            r = requests.post(f"{base}/rest/api/3/issue", headers=headers, json=p, timeout=30)
        if not r.ok:
            hint = ""
            if "issuetype" in r.text:
                hint = (f"\nIssue type '{p['fields']['issuetype']['name']}' is not valid in project {project}. "
                        f"List the valid ones with:\n  curl -s -u \"$JIRA_EMAIL:$JIRA_API_TOKEN\" "
                        f"\"{base}/rest/api/3/issue/createmeta/{project}/issuetypes\"  and set JIRA_ISSUE_TYPE in .env")
            sys.exit(f"Jira said {r.status_code}: {r.text[:500]}{hint}")
        print("created:", r.json().get("key"), "-", p["fields"]["summary"])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    need = ["JIRA_PROJECT_KEY"] if dry else ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
    if not args or [k for k in need if not os.environ.get(k)]:
        sys.exit(__doc__)
    push(args[0], dry_run=dry)
