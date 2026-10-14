"""Ops Copilot agent: meeting transcript -> tasks, decisions, unowned risks and a follow-up email.

Flow
  1. meeting_reader extracts action items (owner, deadline), decisions, risks nobody owns.
  2. A recap email is built from those items (followup.py). It waits for approval.
  3. Everything goes to outbox/<meeting>.json. Nothing is sent. A human runs approve.py
     to approve or reject each draft. notion_push.py puts the items on the Notion board.
  Optional (--finance): if a customer is mentioned with an invoice or payment issue, a
  tool-using loop looks up their invoices and drafts reminders, credit note requests etc.
  The finance tools are plain Python (finance_tools.py), so numbers are exact.

Usage
  python src/agent.py data/transcripts/meeting_01_atlas_sync.txt [--lang de] [--finance]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finance_tools as ft
import followup
import llm
import meeting_reader as mr

ROOT = Path(__file__).resolve().parent.parent
OUTBOX = ROOT / "outbox"
MAX_STEPS = 8

FINANCE_SYSTEM = """You are the finance assistant inside an ops copilot.
For each customer mentioned in a meeting in connection with money, do this:
1. Call get_customer_finance_report with the customer name.
2. If the report shows something to act on (overdue invoices, duplicates, an unallocated payment,
   a credit note candidate), call draft_followups for that customer.
3. If nothing needs action, say so and do not draft anything.
Never state amounts or dates yourself; use only what the tools return.
Drafts are never sent. A human approves them later. Finish with a two-sentence summary."""

FINANCE_TOOLS = [
    {"name": "get_customer_finance_report",
     "description": "Look up a customer's open invoices with aging buckets, duplicate invoices, unallocated payments that match an invoice, and credit note candidates.",
     "input_schema": {"type": "object", "properties": {"customer_name": {"type": "string"}}, "required": ["customer_name"]}},
    {"name": "draft_followups",
     "description": "Create drafts (reminder, dunning letter, credit note request, payment allocation proposal) for a customer. Drafts wait for human approval.",
     "input_schema": {"type": "object", "properties": {"customer_name": {"type": "string"},
                      "language": {"type": "string", "enum": ["en", "de"]}}, "required": ["customer_name"]}},
]


class FinanceToolbox:
    def __init__(self, default_lang="en"):
        self.invoices = ft.load_invoices()
        self.payments = ft.load_payments()
        self.default_lang = default_lang
        self.drafts = []
        self.reports = {}

    def run(self, name, args):
        if name == "get_customer_finance_report":
            rep = ft.customer_report(args["customer_name"], self.invoices, self.payments)
            if rep.get("found"):
                self.reports[rep["customer"]] = rep
            return rep
        if name == "draft_followups":
            rep = ft.customer_report(args["customer_name"], self.invoices, self.payments)
            drafts = ft.draft_messages(rep, args.get("language") or self.default_lang)
            self.drafts.extend(drafts)
            return dict(created=len(drafts), kinds=[d["kind"] for d in drafts])
        return dict(error=f"unknown tool {name}")


def finance_loop(client, mentions, meeting_title, toolbox):
    """Tool-use loop. Returns the assistant's final summary text."""
    if not mentions:
        return "No finance topics in this meeting."
    listing = "\n".join(f"- {m['customer']}: {m['issue']}" for m in mentions)
    messages = [{"role": "user", "content": f"Meeting: {meeting_title}\nFinance topics mentioned:\n{listing}"}]
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=llm.model_name(), max_tokens=1500, system=FINANCE_SYSTEM,
                                      tools=FINANCE_TOOLS, messages=messages, **llm.extra())
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                out = toolbox.run(b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
    return "Stopped: step limit reached."


def run_agent(transcript_path, lang="en", client=None, finance=False):
    transcript_path = Path(transcript_path)
    text = transcript_path.read_text(encoding="utf-8")
    title = text.splitlines()[0].replace("Meeting:", "").strip()
    if client is None:
        client = llm.make_client()

    extracted = mr.read_meeting(text, client)
    toolbox = FinanceToolbox(default_lang=lang)
    if finance:
        summary = finance_loop(client, extracted["finance_mentions"], title, toolbox)
    else:
        summary = "Finance check is off (add --finance to turn it on)."

    source = transcript_path.stem
    tasks = []
    for a in extracted["action_items"]:
        tasks.append(dict(task=a["task"], owner=a["owner"], deadline=a["deadline"], type="Action item",
                          source=source, approval="Not needed", draft="", quote=a["quote"]))
    for d in extracted["decisions"]:
        tasks.append(dict(task=d["decision"], owner="", deadline=None, type="Decision",
                          source=source, approval="Not needed", draft="", quote=d["quote"]))
    for r in extracted["unowned_risks"]:
        tasks.append(dict(task=r["risk"], owner="(no owner)", deadline=None, type="Risk (no owner)",
                          source=source, approval="Not needed", draft="", quote=r["quote"]))
    _, date_str = followup.parse_header(text)
    tasks.append(dict(task=f"Follow-up email - {title}", owner="", deadline=None, type="Follow-up email",
                      source=source, approval="Pending approval",
                      draft=followup.build_followup_email(title, date_str, extracted, lang), quote=""))
    for d in toolbox.drafts:
        tasks.append(dict(task=f"{d['kind'].replace('_', ' ').title()} - {d['customer']}", owner="Finance",
                          deadline=None, type="Finance follow-up", source=source,
                          approval=d["approval"], draft=d["body"], quote=""))

    result = dict(meeting=title, source=source, finance_summary=summary, items=tasks)
    OUTBOX.mkdir(exist_ok=True)
    (OUTBOX / f"{source}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--lang", default="en", choices=["en", "de"])
    ap.add_argument("--finance", action="store_true", help="also check invoices and draft finance follow-ups")
    args = ap.parse_args()
    if not llm.has_key():
        sys.exit(llm.MISSING_KEY_MESSAGE)
    res = run_agent(args.transcript, args.lang, finance=args.finance)
    print(f"Provider: {llm.provider()}, model: {llm.model_name()}")
    print(f"{res['meeting']}: {len(res['items'])} items written to outbox/{res['source']}.json")
    if args.finance:
        print(res["finance_summary"])
