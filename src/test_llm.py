"""Check the provider switch (no network calls)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm

failures = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def env(**kw):
    for k in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPS_COPILOT_PROVIDER", "OPS_COPILOT_MODEL"):
        os.environ.pop(k, None)
    os.environ.update(kw)


env()
check("no keys -> has_key False", not llm.has_key())

env(DEEPSEEK_API_KEY="sk-test")
check("deepseek key -> deepseek provider", llm.provider() == "deepseek")
check("deepseek default model", llm.model_name() == "deepseek-flash")
check("thinking disabled for deepseek", llm.extra() == {"thinking": {"type": "disabled"}})
client = llm.make_client()
check("deepseek client uses DeepSeek URL", str(client.base_url).startswith("https://api.deepseek.com/anthropic"))
check("deepseek has_key", llm.has_key())

env(ANTHROPIC_API_KEY="sk-ant-test")
check("anthropic key -> anthropic provider", llm.provider() == "anthropic")
check("anthropic default model", llm.model_name() == "claude-sonnet-5-5")
check("no extra args for anthropic", llm.extra() == {})

env(DEEPSEEK_API_KEY="a", ANTHROPIC_API_KEY="b", OPS_COPILOT_PROVIDER="anthropic")
check("provider override wins", llm.provider() == "anthropic" and llm.model_name() == "claude-sonnet-5-5")

env(DEEPSEEK_API_KEY="a", OPS_COPILOT_MODEL="deepseek-v4-pro")
check("model override works", llm.model_name() == "deepseek-v4-pro")

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
