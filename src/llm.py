"""LLM gateway: ask for JSON, failing over across every key and model we have.

    from src.llm import ask_json, LLMUnavailable
    data, used = ask_json(system_prompt, user_prompt)   # used = "groq:<model>" | "gemini:<model>" | "ollama:<model>"

Failover chain - the first valid JSON answer wins:
    1. Groq    every key, main model first, then the smaller model (separate rate limit)
    2. Gemini  every key, across a few Flash models (they get overloaded one at a time)
    3. Ollama  local; slow, but needs no internet or quota

Quick, not just robust:
  - A rate limit (429) moves straight to the next key; we never sleep.
  - Cloud calls have short timeouts, so a hung call fails over in seconds.
  - A route that just failed is benched for a while, so the NEXT ticket skips it
    instantly instead of paying the same timeout again. How long, and how wide the
    bench is, depends on what failed: a rejected key, one key's quota on one model,
    an overloaded model, or an unreachable provider.

Groq and Gemini both speak the OpenAI chat format, so one HTTP function serves both.
If everything fails we raise LLMUnavailable and the caller ESCALATEs; there is no
"guess without an LLM" path.

Settings (environment variables or the git-ignored .env file):
    GROQ_API_KEY, GROQ_API_KEY_SPARE_1, _2, ...       keys, tried in that order
    GROQ_MODEL            default openai/gpt-oss-120b
    GROQ_FALLBACK_MODEL   default openai/gpt-oss-20b ("" to disable)
    GEMINI_API_KEY, GEMINI_API_KEY_SPARE_1, _2, ...   keys, tried in that order
    GEMINI_MODELS         comma list, default gemini-3.1-flash-lite,gemini-3.8-flash,gemini-flash-latest
    OLLAMA_MODEL          default qwen2.5:3b
    OLLAMA_URL            default http://localhost:11434
"""
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

try:                                   # optional: read .env if python-dotenv is installed
    from dotenv import load_dotenv     # explicit path: works from any cwd; real env vars still win
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

log = logging.getLogger(__name__)

URL = {"groq": "https://api.groq.com/openai/v1/chat/completions",
       "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"}
# (connect, read) seconds. Cloud answers normally take 1-5 s; local CPU models are slower.
TIMEOUT = {"groq": (3, 20), "gemini": (3, 15), "ollama": (2, 120)}
DEFAULT_GEMINI_MODELS = "gemini-3.1-flash-lite,gemini-3.8-flash,gemini-flash-latest"   # lite first: rarely overloaded, ~1.5 s


class LLMUnavailable(RuntimeError):
    """No provider, key or model produced valid JSON."""


@dataclass(frozen=True)
class Route:
    provider: str      # "groq" | "gemini" | "ollama"
    model: str
    key: str = ""      # never logged; see .label
    key_no: int = 0    # 1 = main key, 2 = first spare, ...

    @property
    def label(self) -> str:            # safe to log: names the key by position, not value
        return f"{self.provider}#{self.key_no}:{self.model}" if self.key else f"{self.provider}:{self.model}"

    @property
    def key_id(self) -> str:
        return hashlib.sha256(self.key.encode()).hexdigest()[:10]


# ── which routes exist ──────────────────────────────────────────────────────

def _keys(name: str) -> list[str]:
    """NAME, then NAME_SPARE_1, NAME_SPARE_2, ... (numeric order), without blanks or duplicates."""
    spares = sorted((int(m.group(1)), v) for k, v in os.environ.items()
                    if (m := re.fullmatch(rf"{name}_SPARE_(\d+)", k)))
    out = []
    for key in [os.getenv(name, "")] + [v for _, v in spares]:
        key = key.strip()
        if key and key not in out:
            out.append(key)
    return out


def routes() -> list[Route]:
    """The failover chain, in the order it is tried. Read fresh each call so key changes apply at once."""
    chain = []
    groq_models = [os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")]
    gemini_models = [m.strip() for m in os.getenv("GEMINI_MODELS", DEFAULT_GEMINI_MODELS).split(",")]
    for provider, models, keys in (("groq", groq_models, _keys("GROQ_API_KEY")),
                                   ("gemini", gemini_models, _keys("GEMINI_API_KEY"))):
        for model in dict.fromkeys(m for m in models if m):          # dedupe, keep order
            for n, key in enumerate(keys, 1):                         # model-major: best model on every key first
                chain.append(Route(provider, model, key, n))
    chain.append(Route("ollama", os.getenv("OLLAMA_MODEL", "qwen2.5:3b")))
    return chain


# ── bench: remember what just failed so the next call skips it ──────────────
_bench: dict[str, float] = {}          # bench name -> time.monotonic() when it may be tried again


def _names(r: Route) -> dict[str, str]:
    return {"provider": f"provider:{r.provider}",
            "model": f"model:{r.provider}:{r.model}",
            "key": f"key:{r.key_id}",
            "route": f"route:{r.key_id}:{r.model}"}


def is_benched(r: Route) -> bool:
    now = time.monotonic()
    return any(_bench.get(n, 0) > now for n in _names(r).values())


def _bench_for(r: Route, scope: str, seconds: float) -> None:
    name = _names(r)[scope]
    _bench[name] = max(_bench.get(name, 0), time.monotonic() + seconds)


def _retry_after(resp: requests.Response, default: float = 20) -> float:
    try:
        return min(float(resp.headers.get("retry-after", default)), 300)
    except ValueError:
        return default


def _on_failure(r: Route, e: Exception) -> str:
    """Bench the right thing for this failure; return a short reason (never contains the key)."""
    resp = getattr(e, "response", None)
    status = resp.status_code if resp is not None else None
    if status in (401, 403):
        _bench_for(r, "key", 3600)
        return f"HTTP {status} key rejected"
    if status == 429:
        _bench_for(r, "route", _retry_after(resp))
        return "HTTP 429 rate limit"
    if status == 404:
        _bench_for(r, "model", 3600)
        return "HTTP 404 model not available"
    if status is not None and status >= 500:
        _bench_for(r, "model", 120)                    # overload spikes last minutes, not seconds
        return f"HTTP {status} provider overloaded"
    if isinstance(e, requests.ConnectionError):        # also catches ConnectTimeout: provider unreachable
        _bench_for(r, "provider", 30)
        return "unreachable"
    if isinstance(e, requests.Timeout):            # a hung model is an overloaded model
        _bench_for(r, "model", 120)
        return "timed out"
    # HTTP 400 (often "model output was not valid JSON") or unparseable answer:
    # specific to this prompt, so nothing is benched - the next route just tries it.
    return f"{type(e).__name__}: {str(e)[:100]}" if status is None else f"HTTP {status}"


# ── calling one route ───────────────────────────────────────────────────────

def _call(r: Route, messages: list[dict]) -> str:
    if r.provider == "ollama":
        url = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
        resp = requests.post(url, timeout=TIMEOUT["ollama"],
                             json={"model": r.model, "messages": messages, "stream": False, "format": "json",
                                   "options": {"temperature": 0}})
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    resp = requests.post(URL[r.provider], timeout=TIMEOUT[r.provider],
                         headers={"Authorization": f"Bearer {r.key}"},
                         json={"model": r.model, "messages": messages, "temperature": 0,
                               "response_format": {"type": "json_object"}})
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def ask_json(system: str, user: str) -> tuple[dict, str]:
    """Return (parsed JSON answer, "provider:model" that answered)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    chain = routes()
    if all(is_benched(r) for r in chain):
        _bench.clear()                                 # everything benched: forget it and take one fresh pass
    errors = []
    for r in chain:
        if is_benched(r):                              # checked per route, so a failure benches its siblings
            continue                                   # in THIS call too (other keys of a dead model, etc.)
        started = time.monotonic()
        try:
            data = json.loads(_call(r, messages))
            if not isinstance(data, dict):
                raise ValueError("answer is JSON but not an object")
            if errors:
                log.warning("LLM answered via %s after %d failover(s)", r.label, len(errors))
            return data, f"{r.provider}:{r.model}"
        except Exception as e:                         # noqa: BLE001 - any failure -> next route
            why = _on_failure(r, e)
            errors.append(f"{r.label}: {why}")
            log.warning("LLM %s failed after %.1fs (%s); trying next", r.label, time.monotonic() - started, why)
    raise LLMUnavailable("; ".join(errors))
