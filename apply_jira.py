"""Run once from the project folder:  python3 apply_jira.py
Adds the Jira settings to docker-compose.yml, Makefile, .env.example and the offline test run."""
import re
from pathlib import Path

def edit(path, fn):
    p = Path(path); s = p.read_text(encoding="utf-8"); n = fn(s)
    if n == s: print("already done:", path)
    else: p.write_text(n, encoding="utf-8"); print("updated:", path)

def compose(s):
    if "JIRA_BASE_URL" in s: return s
    s = s.replace("    NOTION_DATABASE_ID: ${NOTION_DATABASE_ID:-}\n",
        "    NOTION_DATABASE_ID: ${NOTION_DATABASE_ID:-}\n"
        "    JIRA_BASE_URL: ${JIRA_BASE_URL:-}\n    JIRA_EMAIL: ${JIRA_EMAIL:-}\n"
        "    JIRA_API_TOKEN: ${JIRA_API_TOKEN:-}\n    JIRA_PROJECT_KEY: ${JIRA_PROJECT_KEY:-}\n"
        "    JIRA_ISSUE_TYPE: ${JIRA_ISSUE_TYPE:-}\n", 1)
    s = s.replace("             python src/test_llm.py\"", "             python src/test_llm.py &&\n             python src/test_jira.py\"", 1)
    block = ("  # Push an outbox file to Jira: OUTBOX_FILE=outbox/<name>.json (JIRA_FLAGS=--dry-run to preview)\n"
             "  jira:\n    <<: *common\n    profiles: [\"tools\"]\n"
             "    command: python src/jira_push.py ${OUTBOX_FILE:-} ${JIRA_FLAGS:-}\n\n")
    return s.replace("  # Regenerate the fake invoice", block + "  # Regenerate the fake invoice", 1)

def make(s):
    s = s.replace("\t$(RUN) -e ACTION=reject approve", "\tACTION=reject $(RUN) approve")
    if "jira:" in s: return s
    s = s.replace("push shell data", "push jira shell data", 1)
    t = ("jira: need-file dirs build ## Push an outbox file to Jira: make jira OUTBOX_FILE=outbox/<name>.json [DRY=1]\n"
         "\tJIRA_FLAGS=$(if $(DRY),--dry-run,) $(RUN) jira\n\n")
    return s.replace("shell: dirs build", t + "shell: dirs build", 1)

def env(s):
    if "JIRA_BASE_URL" in s: return s
    return s.rstrip("\n") + ("\n\n# --- Optional: Jira Cloud (needed only for `make jira`) ---\n"
        "JIRA_BASE_URL=https://your-site.atlassian.net\nJIRA_EMAIL=\nJIRA_API_TOKEN=\nJIRA_PROJECT_KEY=\nJIRA_ISSUE_TYPE=Task\n")

edit("docker-compose.yml", compose); edit("Makefile", make); edit(".env.example", env)
