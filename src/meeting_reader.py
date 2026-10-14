"""Step 1 of the Ops Copilot: read a meeting transcript and return structured items.

The model is forced to answer through a tool (record_meeting), so the output is always
valid JSON that matches the schema below.
"""
import json
import os
import sys
from pathlib import Path

import llm  # provider switch: DeepSeek or Anthropic

SYSTEM = """You turn meeting transcripts into structured project data.

Rules:
- action_items: only concrete commitments someone made or accepted. One owner (first name) per item.
  Resolve relative dates ("by Wednesday", "before the 16th") to ISO dates using the meeting date given.
  If no deadline was said, use null. Do not invent owners or deadlines.
- decisions: things the group explicitly decided.
- unowned_risks: real problems raised in the meeting that nobody took responsibility for.
  Only list something that could cause actual harm (lost money, missed deadline, outdated or broken process)
  AND that the speakers treated as needing attention. Do NOT list: jokes or small talk, anything the speaker
  calls minor or unimportant, pros and cons of an option that is still being discussed, or topics the group
  explicitly postponed on purpose. If a problem has someone assigned to it, it is not unowned.
- finance_mentions: any customer named in connection with an invoice, payment, credit note,
  reminder or billing issue. Use the customer name as spoken. Put a short issue summary.
- Include a short supporting quote (max 15 words) for each item so a human can verify it.
- Never include information that is not in the transcript."""

RECORD_TOOL = {
    "name": "record_meeting",
    "description": "Record the structured result of reading the meeting transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action_items": {"type": "array", "items": {"type": "object", "properties": {
                "task": {"type": "string"}, "owner": {"type": "string"},
                "deadline": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD or null"},
                "quote": {"type": "string"}}, "required": ["task", "owner", "deadline", "quote"]}},
            "decisions": {"type": "array", "items": {"type": "object", "properties": {
                "decision": {"type": "string"}, "quote": {"type": "string"}}, "required": ["decision", "quote"]}},
            "unowned_risks": {"type": "array", "items": {"type": "object", "properties": {
                "risk": {"type": "string"}, "quote": {"type": "string"}}, "required": ["risk", "quote"]}},
            "finance_mentions": {"type": "array", "items": {"type": "object", "properties": {
                "customer": {"type": "string"}, "issue": {"type": "string"}}, "required": ["customer", "issue"]}},
        },
        "required": ["action_items", "decisions", "unowned_risks", "finance_mentions"],
    },
}


def validate(result):
    """Light validation so bad output is caught early."""
    for key in ("action_items", "decisions", "unowned_risks", "finance_mentions"):
        if not isinstance(result.get(key), list):
            raise ValueError(f"missing list: {key}")
    for a in result["action_items"]:
        if not a.get("task") or not a.get("owner"):
            raise ValueError(f"action item without task or owner: {a}")
        dl = a.get("deadline")
        if dl is not None and (len(dl) != 10 or dl[4] != "-" or dl[7] != "-"):
            raise ValueError(f"deadline is not ISO: {dl}")
    return result


def read_meeting(transcript_text, client=None):
    if client is None:
        client = llm.make_client()
    resp = client.messages.create(
        model=llm.model_name(), max_tokens=2000, system=SYSTEM, tools=[RECORD_TOOL],
        tool_choice={"type": "tool", "name": "record_meeting"},
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
        **llm.extra(),
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    return validate(block.input)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    print(json.dumps(read_meeting(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))