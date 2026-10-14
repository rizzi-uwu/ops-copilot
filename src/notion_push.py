"""Push an outbox file to the Notion task board.

Setup (once):
  1. notion.so/profile/integrations -> create an internal integration, copy the token.
  2. Open the 'Ops Copilot Task Board' database -> ... menu -> Connections -> add your integration.
  3. export NOTION_TOKEN=...   and   export NOTION_DATABASE_ID=6084e5fea946457bb2018724cf52fc1b

Usage:
  python src/notion_push.py outbox/meeting_05_month_end_finance.json
"""
import json
import os
import sys
from pathlib import Path

NOTION_VERSION = "2022-06-28"


def _text(s, limit=1900):
    return [{"type": "text", "text": {"content": (s or "")[:limit]}}]


def build_payload(item, database_id, meeting):
    props = {
        "Task": {"title": _text(item["task"], 200)},
        "Owner": {"rich_text": _text(item["owner"])},
        "Status": {"status": {"name": "Not started"}},
        "Type": {"select": {"name": item["type"]}},
        "Source meeting": {"rich_text": _text(meeting)},
        "Approval": {"select": {"name": item["approval"]}},
        "Draft": {"rich_text": _text(item["draft"])},
    }
    if item.get("deadline"):
        props["Deadline"] = {"date": {"start": item["deadline"]}}
    return {"parent": {"database_id": database_id}, "properties": props}


def push(outbox_file):
    import requests
    token, db = os.environ["NOTION_TOKEN"], os.environ["NOTION_DATABASE_ID"]
    data = json.loads(Path(outbox_file).read_text(encoding="utf-8"))
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}
    for item in data["items"]:
        r = requests.post("https://api.notion.com/v1/pages", headers=headers,
                          json=build_payload(item, db, data["meeting"]), timeout=30)
        r.raise_for_status()
        print("created:", item["task"])


if __name__ == "__main__":
    if not (os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_DATABASE_ID")):
        sys.exit(__doc__)
    push(sys.argv[1])
