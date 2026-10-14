"""Human approval step. Lists drafts waiting for approval and lets you approve or reject them.

  python src/approve.py            # list pending drafts
  python src/approve.py approve meeting_05_month_end_finance 2
  python src/approve.py reject  meeting_05_month_end_finance 2

'Approve' only marks the draft as approved in the outbox. Sending is deliberately a separate,
manual step in this demo.
"""
import json
import sys
from pathlib import Path

OUTBOX = Path(__file__).resolve().parent.parent / "outbox"


def pending():
    rows = []
    for f in sorted(OUTBOX.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for idx, it in enumerate(data["items"]):
            if it["approval"] == "Pending approval":
                rows.append((f.stem, idx, it))
    return rows


def set_status(source, idx, status):
    f = OUTBOX / f"{source}.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    item = data["items"][idx]
    if item["approval"] != "Pending approval":
        sys.exit(f"Item {idx} is '{item['approval']}', not pending.")
    item["approval"] = status
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{source} #{idx} -> {status}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        for src, idx, it in pending():
            print(f"[{src} #{idx}] {it['task']}\n{it['draft']}\n{'-' * 60}")
    elif len(sys.argv) == 4 and sys.argv[1] in ("approve", "reject"):
        set_status(sys.argv[2], int(sys.argv[3]), "Approved" if sys.argv[1] == "approve" else "Rejected")
    else:
        sys.exit(__doc__)
