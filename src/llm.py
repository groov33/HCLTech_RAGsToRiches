"""LLM gateway: ask for JSON, Groq first, local Ollama if Groq fails.

    from src.llm import ask_json, LLMUnavailable
    data, used = ask_json(system_prompt, user_prompt)   # used = "groq:<model>" or "ollama:<model>"

Plain HTTP (requests), no vendor SDKs: both providers accept a chat request and
can be told to answer in JSON. Each provider gets one retry if the answer is not
valid JSON. If both fail we raise LLMUnavailable and the caller ESCALATEs; there
is no "guess without an LLM" path.

Settings (environment variables or a git-ignored .env file):
    GROQ_API_KEY   - without it, Groq is skipped
    GROQ_MODEL     - default llama-3.3-70b-versatile
    OLLAMA_MODEL   - default qwen2.5:3b (the model installed on this machine)
    OLLAMA_URL     - default http://localhost:11434
"""
import json
import os

import requests

try:                                   # optional: read .env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = {"groq": 30, "ollama": 120}  # seconds; local CPU models are slower


class LLMUnavailable(RuntimeError):
    """Neither Groq nor Ollama produced valid JSON."""


def _groq(messages: list[dict]) -> tuple[str, str]:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("no GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    r = requests.post(GROQ_URL, timeout=TIMEOUT["groq"], headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "messages": messages, "temperature": 0,
                            "response_format": {"type": "json_object"}})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"], f"groq:{model}"


def _ollama(messages: list[dict]) -> tuple[str, str]:
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
    r = requests.post(url, timeout=TIMEOUT["ollama"],
                      json={"model": model, "messages": messages, "stream": False, "format": "json",
                            "options": {"temperature": 0}})
    r.raise_for_status()
    return r.json()["message"]["content"], f"ollama:{model}"


def ask_json(system: str, user: str) -> tuple[dict, str]:
    """Return (parsed JSON answer, which provider answered)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    errors = []
    for provider in (_groq, _ollama):
        for _attempt in range(2):                     # one retry on bad JSON / network blip
            try:
                text, used = provider(messages)
                return json.loads(text), used
            except Exception as e:                    # noqa: BLE001 - any failure -> next try
                errors.append(f"{provider.__name__[1:]}: {type(e).__name__}: {str(e)[:120]}")
                if "no GROQ_API_KEY" in str(e):
                    break                             # no point retrying without a key
    raise LLMUnavailable("; ".join(errors))
