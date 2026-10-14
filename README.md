# Ops Copilot

An agent that turns meeting transcripts into tasks, decisions, risks nobody owns, and a follow-up email. A person approves before anything is sent. An optional finance module can also check invoices when a customer is mentioned.

All data in this repo is invented (fictional people, customers, amounts and meetings).

## What it does

1. **Reads a meeting transcript** with an LLM and returns action items (owner, deadline), decisions, and risks nobody took responsibility for. Every item carries a short quote from the transcript so a person can verify it.
2. **Drafts a recap email** (English or German) from those items. It is built from a template, so it can only contain what was extracted.
3. **Writes everything to `outbox/<meeting>.json`** and, with `notion_push.py`, to a Notion board with Type, Owner, Deadline and Approval columns.
4. **Waits for approval.** The email is marked "Pending approval". Nothing is sent automatically.

Optional (`--finance`): if a meeting mentions a customer with an invoice or payment issue, the agent looks up that customer's invoices and payments (plain Python tools: payment matching, duplicate detection, aging buckets) and drafts reminders, dunning letters or credit note requests. These need approval too. Amounts and dates come from code, never from the model.

## Why it is built this way

- The model understands language (who promised what by when). Templates and code handle the rest, so nothing gets invented in outgoing text.
- Risks that nobody owns are listed on their own. This is the thing meetings usually drop.
- Every item can be traced to a quote, and every outgoing draft needs a human decision.

## Run it with Docker (recommended)

Needs Docker with Compose, and `make` (on Windows use WSL, or run the `docker compose` commands shown in `docker-compose.yml` directly).

```bash
make setup        # creates .env; open it and paste your DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY)
make test         # offline checks, no key needed
make run          # agent on one sample meeting (results in ./outbox)
make run TRANSCRIPT=data/transcripts/meeting_01_atlas_sync.txt LETTER_LANG=de
make run-all      # all 10 sample meetings
make run FINANCE=1   # also run the optional finance check
make evaluate     # accuracy check on the 10 sample meetings (basic and hard sets)
make approve-list # drafts waiting for approval
make approve SOURCE=meeting_05_month_end_finance N=6   # use the #number shown in the list
make push OUTBOX_FILE=outbox/meeting_05_month_end_finance.json   # needs NOTION_TOKEN in .env
make help         # full list
```

`./src`, `./data` and `./outbox` are mounted into the container, so you can edit prompts, transcripts and code without rebuilding. Rebuild (`make build`) only after changing `requirements.txt`.

## Run it without Docker

The model provider is switchable. DeepSeek is used through its Anthropic-compatible endpoint, so the same code runs on either provider.

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY=...                  # DeepSeek (model: deepseek-flash)
# or: export ANTHROPIC_API_KEY=...           # Anthropic (model: claude-sonnet-5-5)
python src/agent.py data/transcripts/meeting_05_month_end_finance.txt --lang de
python src/agent.py data/transcripts/meeting_05_month_end_finance.txt --finance
python src/approve.py                        # list drafts waiting for approval
python src/approve.py approve meeting_05_month_end_finance 6
python src/evaluate.py                       # accuracy check on the 10 sample meetings
python src/make_data.py                      # regenerate the fake data and the labels
```

Optional: `src/notion_push.py` writes an outbox file to a Notion database (setup steps are in the file).

## Accuracy check

`evaluate.py` runs the reader on 10 sample meetings and compares with hand-written labels in `data/expected.json`. The two sets are reported separately:

- **Basic (meetings 1-5):** clear phrasing, like "I'll do X by Friday".
- **Hard (meetings 6-10):** a commitment that is corrected and one that is retracted (the owner changes mid-meeting), vague and relative dates ("Friday next week"), assignment by answering "sure, I can take it", a conditional commitment, a German meeting, a mixed German/English meeting, ideas that are not decisions, hypotheticals that are not commitments, and a meeting with no decisions at all.

Scores:

- **Action recall:** share of the labelled action items found with the right owner, and the right deadline where the transcript gives one clear date.
- **Action precision:** share of extracted action items that match a label.
- **Decisions and risks:** whether the count matches.

It does not score the wording of items. The labels are one person's reading of invented transcripts, and 10 meetings is a small sample, so treat the result as a smoke test, not a benchmark. Read a few outputs by hand too. If you change the prompt after seeing a result, say so: the set you tuned on is no longer a clean test.

### Evaluation log

- **Basic set, first run (DeepSeek, `deepseek-flash`):** 18/18 action items found with the correct owner (12 also checked on the exact deadline, 6 on owner only). Decisions right in 5/5 meetings. Unowned risks right in 4/5. The miss: in `meeting_03_sprint_planning` the model also listed a remark the speaker called minor ("the new icons are still unclear on small screens, but that's minor") as a second risk.
- **Hard set, first run (same model, before any prompt change):** 14/14 action items found, 14/14 extracted match. Decisions right in 5/5. Unowned risks right in only 3/5. Over all 10 meetings: actions 32/32 found, 32/33 precise; decisions 10/10; risks 7/10. All three risk misses are over-reporting: a remark called minor (meeting_03), a coffee-machine joke (meeting_09), and, in the discussion-only meeting_10, 3 extra "risks" that were really pros and cons of an option plus a postponed topic. Meeting_04's one extra action (Lena: "we'll follow up" on a replacement contact) is arguably a real commitment that my labels missed, so that is a label gap, not a model error. Labels were left unchanged.
- **Prompt tightened once after seeing these results** (`unowned_risks` now excludes jokes, remarks called minor, option pros/cons and deliberately postponed topics). These 10 meetings are no longer a clean test for risks. 
- **Re-run after the prompt change (tuned, not a clean test):** actions 32/32 found, 32/33 precise (the one extra is the meeting_04 follow-up, a label gap); decisions 10/10; unowned risks 10/10 (was 7/10). The risk fix was written after seeing these same 10 meetings, so treat 10/10 as "the known failures are fixed", not as expected accuracy on new meetings. A clean estimate needs new meetings that the prompt has not seen.

## Tests

```bash
python src/test_finance.py          # finance logic vs hand-derived expected results
python src/test_agent_plumbing.py   # agent wiring, follow-up email, scoring (scripted stand-in model)
python src/test_llm.py              # provider switch (DeepSeek / Anthropic)
```

## What is real and what is simulated

- Real: transcript reading with an LLM (DeepSeek or Claude), structured extraction, follow-up email draft, approval step, optional finance tools and drafts.
- Simulated: all meetings and finance data are invented. Sending emails is not implemented on purpose.

**Live example:** [Notion board with the agent's output] (all data is invented)
cat >> README.md <<'EOF'


---

<p align="center">
  <a href="https://app.notion.com/p/6084e5fea946457bb2018724cf52fc1b?v=13131d54207a47f5a3ce6b9c5d9edff3&source=copy_link">
    <img src="https://img.shields.io/badge/Notion-See%20the%20agent's%20output-000000?style=for-the-badge&logo=notion&logoColor=white" alt="See the agent's output on Notion">
  </a>
  <br>
  <sub>Live example board. All data is invented.</sub>
</p>
EOF
git add README.md
git commit -m "Add Notion board button"
git push
