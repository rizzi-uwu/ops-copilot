"""Provider switch: DeepSeek or Anthropic, same code.

DeepSeek offers an Anthropic-compatible endpoint, so we use the same SDK and only change the
base URL, the key and the model name.

  DeepSeek (default if DEEPSEEK_API_KEY is set):
      export DEEPSEEK_API_KEY=sk-...
  Anthropic (for the hackathon, when you get credits):
      export ANTHROPIC_API_KEY=sk-ant-...
      (and unset DEEPSEEK_API_KEY, or export OPS_COPILOT_PROVIDER=anthropic)

Optional: OPS_COPILOT_MODEL overrides the model name.
"""
import os

DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5-5"


def provider():
    forced = os.environ.get("OPS_COPILOT_PROVIDER", "").lower()
    if forced in ("deepseek", "anthropic"):
        return forced
    return "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else "anthropic"


def has_key():
    return bool(os.environ.get("DEEPSEEK_API_KEY") if provider() == "deepseek" else os.environ.get("ANTHROPIC_API_KEY"))


def model_name():
    default = DEEPSEEK_DEFAULT_MODEL if provider() == "deepseek" else ANTHROPIC_DEFAULT_MODEL
    return os.environ.get("OPS_COPILOT_MODEL") or default


def make_client():
    import anthropic
    if provider() == "deepseek":
        return anthropic.Anthropic(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=DEEPSEEK_BASE_URL)
    return anthropic.Anthropic()


def extra():
    """Extra request arguments. DeepSeek rejects a forced tool call while thinking mode is on,
    so thinking is switched off for DeepSeek."""
    return {"thinking": {"type": "disabled"}} if provider() == "deepseek" else {}


MISSING_KEY_MESSAGE = ("No API key found. Set one of:\n"
                       "  export DEEPSEEK_API_KEY=...    (DeepSeek)\n"
                       "  export ANTHROPIC_API_KEY=...   (Anthropic)")
