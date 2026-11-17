"""The ONLY module pages talk to. It calls src/*; pages never import src/ directly.

Kept free of Streamlit so it can be tested from a plain Python shell:
    python -c "from app import backend; print(backend.system_status())"
"""
from __future__ import annotations

import csv
import io
import json
import os
import secrets
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from src import store
from src.contracts import CONTRACT_VERSION, check_result  # noqa: F401  (re-exported for pages)
from src.text import mask_pii

ROOT = Path(__file__).resolve().parents[1]
TICKETS_PATH = ROOT / "data" / "resolveiq_tickets.jsonl"
EVAL_PATH = ROOT / "reports" / "eval_results.json"
RAG_EVAL_PATH = ROOT / "reports" / "rag_eval_results.json"
MODEL_PATH = ROOT / "data" / "store" / "models" / "classifier.joblib"
INDEX_PATH = ROOT / "data" / "store" / "chroma"
ENV_PATH = ROOT / ".env"
try:                                                   # status badges must see .env keys before the
    from dotenv import load_dotenv                     # first ticket imports src/llm.py
    load_dotenv(ENV_PATH)
except ImportError:
    pass

# SIMULATED manual-handling minutes per priority (no real history in our data). Shown as "Simulated baseline".
BASELINE_MIN = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2880}
GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]   # first = default; must match src/llm.py

BUILD_COMMANDS = {
    "model file": "python -m build.train_models",
    "search index": "python -m build.build_index",
    "evaluation": "python -m build.run_eval",
    "search evaluation": "python -m build.run_rag_eval",
}


class BackendError(RuntimeError):
    """A friendly, user-facing problem (never contains secrets or tracebacks)."""

    def __init__(self, message: str, command: str | None = None):
        super().__init__(message)
        self.command = command


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Pipeline ────────────────────────────────────────────────────────────────
def _check_built() -> None:
    if not MODEL_PATH.exists():
        raise BackendError("Model not trained yet.", BUILD_COMMANDS["model file"])
    if not INDEX_PATH.exists():
        raise BackendError("Search index not built yet.", BUILD_COMMANDS["search index"])


def warmup() -> None:
    """Load the classifier, embedding model and indexes once (first load takes ~30 s)."""
    _check_built()
    from src import pipeline
    pipeline._classifier()
    pipeline._retriever()


def analyze_ticket(ticket: dict, role: str, analyst: str, use_llm: bool = True) -> dict:
    """Run the 9-step pipeline, store the audit record, return an AnalysisResult."""
    _check_built()
    from src.pipeline import analyze_ticket as run
    try:
        result = run(ticket, role=role, analyst=analyst or "anonymous", use_llm=use_llm)
    except BackendError:
        raise
    except Exception as e:  # noqa: BLE001 - never show a traceback in the UI
        print(f"[backend] analyze_ticket failed: {type(e).__name__}: {str(e)[:200]}")
        raise BackendError(f"The analysis failed ({type(e).__name__}). Check the console for details.") from None
    result["missing_parts"] = [p for p in result.get("missing_parts", []) if p != "store"]  # store.py now exists
    try:
        store.save_analysis(result)
    except Exception as e:  # noqa: BLE001
        print(f"[backend] could not save analysis: {type(e).__name__}: {e}")
        result["missing_parts"].append("store")
    return result


def ask_kb(question: str, role: str = "employee") -> dict:
    """KB Assistant. Employees get public articles + self-help steps only (filter applied before search)."""
    _check_built()
    from src.pipeline import ask_kb as run
    try:
        return run(question, role=role)
    except Exception as e:  # noqa: BLE001
        print(f"[backend] ask_kb failed: {type(e).__name__}: {str(e)[:200]}")
        raise BackendError("The knowledge base search failed. Check the console for details.") from None


def thresholds() -> dict:
    """The live thresholds the pipeline uses, for the Trace tab (read from src, never copied)."""
    from src import classify, decide, resolve, retrieve
    return {"Accept category score (else REVIEW)": classify.ACCEPT_THRESHOLD,
            "Security alert probability": classify.SECURITY_ALERT_PROB,
            "Possible duplicate similarity": retrieve.DUPLICATE_SIM,
            "KB floor (below = knowledge gap)": retrieve.KB_FLOOR,
            "Citation match (0-100)": resolve.MIN_MATCH,
            "Minimum decision confidence": decide.MIN_CONFIDENCE}


# ── Past tickets (dataset) ──────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _tickets() -> pd.DataFrame:
    df = pd.read_json(TICKETS_PATH, lines=True)
    df["description"] = df["description"].map(mask_pii)
    return df


def list_tickets(filters: dict | None = None, role: str = "support") -> pd.DataFrame:
    """Dataset tickets, PII masked. filters: {column: [values]} plus optional "text": str."""
    if role not in ("support", "admin"):
        raise PermissionError("Past tickets are for Support only.")
    df, filters = _tickets(), filters or {}
    for col, values in filters.items():
        if col == "text":
            if values:
                df = df[df["description"].str.contains(str(values), case=False, regex=False)
                        | df["ticket_id"].str.contains(str(values), case=False, regex=False)]
        elif values:
            df = df[df[col].isin(values)]
    return df.reset_index(drop=True)


def get_ticket(ticket_id: str, role: str = "support") -> dict | None:
    df = list_tickets({}, role)
    row = df[df["ticket_id"] == ticket_id]
    return row.iloc[0].to_dict() if len(row) else None


# ── Knowledge base ──────────────────────────────────────────────────────────
def list_kb(filters: dict | None = None, role: str = "admin") -> list[dict]:
    """Full articles the role may see, each with a "steps" list of citable step IDs.

    Returns raw article dicts (not KBHit): the Knowledge base page needs symptoms, cause, etc.
    filters: {"category": [...], "subcategory": [...], "access_level": [...], "service": [...], "text": str}
    """
    from src.kb import access_for, article_steps, load_articles
    access, filters = access_for(role), filters or {}
    out = []
    for a in load_articles().values():
        if a.get("access_level", "public") not in access["levels"]:
            continue
        if filters.get("category") and a["category"] not in filters["category"]:
            continue
        if filters.get("subcategory") and a["subcategory"] not in filters["subcategory"]:
            continue
        if filters.get("access_level") and a.get("access_level") not in filters["access_level"]:
            continue
        if filters.get("service") and not set(a.get("services", [])) & set(filters["service"]):
            continue
        text = (filters.get("text") or "").lower()
        if text and text not in json.dumps(a).lower():
            continue
        out.append({**a, "steps": article_steps(a, tuple(access["step_types"]))})
    return out


# ── Feedback, audit, MTTR ───────────────────────────────────────────────────
def add_feedback(record: dict) -> None:
    """Store a FeedbackRecord. feedback_id / created_at are filled in if missing."""
    record = {"feedback_id": f"FB-{secrets.token_hex(4)}", "created_at": _now(), "comment": "", **record}
    record["comment"] = mask_pii(record.get("comment") or "")
    store.add_feedback(record)


def get_feedback(analyst: str | None = None) -> list[dict]:
    return store.list_feedback(analyst)


def mark_resolved(analysis_id: str) -> str | None:
    return store.mark_resolved(analysis_id)


def get_audit(filters: dict | None = None) -> list[dict]:
    """filters: {"outcome": [...], "priority": [...], "analyst": str}"""
    f = filters or {}
    return store.list_analyses(f.get("outcome"), f.get("priority"), f.get("analyst") or None)


def _audit_row(r: dict) -> dict:
    lab, dec, ts = r["classification"], r["decision"], r["timestamps"]
    feedback = [f for f in store.list_feedback() if f["analysis_id"] == r["analysis_id"]]
    return {
        "analysis_id": r["analysis_id"], "analyst": r["analyst"], "role": r["role"],
        "created_at": ts["created_at"], "recommended_at": ts["recommended_at"], "resolved_at": ts["resolved_at"],
        "service": r["ticket"].get("service"), "description": r["ticket"].get("description"),
        "category": lab["category"], "subcategory": lab["subcategory"], "priority": lab["priority"],
        "category_score": lab["confidence"]["category_score"], "outcome": dec["outcome"],
        "confidence": dec["confidence"], "reasons": " | ".join(dec["reasons"]),
        "similar_tickets": " ".join(t["ticket_id"] for t in (r.get("similar") or {}).get("tickets", [])),
        "kb_articles": " ".join(a["kb_id"] for a in (r.get("kb") or {}).get("articles", [])),
        "fix_steps": " | ".join(s["text"] for p in (r.get("fix") or {}).get("paths", []) for s in p["steps"]),
        "feedback": " | ".join(f"{f['target_id']}={f['verdict']}" for f in feedback),
    }


def export_audit(filters: dict | None = None, fmt: str = "csv") -> bytes:
    """Audit export, PII masked a second time as a safety net."""
    records = get_audit(filters)
    if fmt == "json":
        return mask_pii(json.dumps(records, indent=1)).encode("utf-8")
    rows = [_audit_row(r) for r in records]
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: mask_pii(str(v)) if v is not None else "" for k, v in row.items()} for row in rows)
    return buf.getvalue().encode("utf-8")


def _minutes(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60


def get_mttr() -> dict:
    """MTTRReport: simulated baseline vs assisted (resolved_at - created_at), per priority."""
    analyses = store.list_analyses()
    rows, base_total, assist_total = [], 0.0, 0.0
    for p, baseline in BASELINE_MIN.items():
        mine = [a for a in analyses if a["classification"]["priority"] == p]
        resolved = [m for m in (_minutes(a["timestamps"]["created_at"], a["timestamps"]["resolved_at"])
                                for a in mine) if m is not None]
        to_rec = [m for m in (_minutes(a["timestamps"]["created_at"], a["timestamps"]["recommended_at"])
                              for a in mine) if m is not None]
        assisted = sum(resolved) / len(resolved) if resolved else None
        rows.append({"priority": p, "baseline_min": baseline, "assisted_min": assisted,
                     "to_recommendation_min": sum(to_rec) / len(to_rec) if to_rec else None,
                     "n_resolved": len(resolved)})
        if resolved:
            base_total += baseline * len(resolved)
            assist_total += sum(resolved)
    reduction = round(100 * (1 - assist_total / base_total), 1) if base_total else None
    return {"rows": rows, "overall_reduction_pct": reduction, "baseline_is_simulated": True}


# ── Evaluation ──────────────────────────────────────────────────────────────
def get_eval() -> dict | None:
    """reports/eval_results.json as-is, plus key "rag" = reports/rag_eval_results.json (or None)."""
    if not EVAL_PATH.exists():
        return None
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    data["rag"] = json.loads(RAG_EVAL_PATH.read_text(encoding="utf-8")) if RAG_EVAL_PATH.exists() else None
    return data


# ── LLM settings + system status ────────────────────────────────────────────
_groq_checked: dict[str, str] = {}   # key fingerprint -> "ok" | "error"   (key itself never stored here)


def _fingerprint(key: str) -> str:
    return f"{len(key)}:{key[-4:]}"


def masked_key() -> str | None:
    key = os.getenv("GROQ_API_KEY")
    return f"{key[:4]}••••{key[-4:]}" if key and len(key) > 8 else ("••••" if key else None)


def _test_groq(key: str) -> str:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", timeout=8,
                         headers={"Authorization": f"Bearer {key}"})
        return "ok" if r.status_code == 200 else "error"
    except requests.RequestException:
        return "error"


def _ollama_up() -> bool:
    try:
        # 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first, and a closed port
        # there waits out the whole timeout before IPv4 is tried. The sidebar runs this every 30 s.
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        return requests.get(url + "/api/tags", timeout=0.5).status_code == 200
    except requests.RequestException:
        return False


def llm_status() -> dict:
    """LLMStatus. Groq is tested once per key per process (a free /models call, no tokens)."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        groq = "no key"
    else:
        fp = _fingerprint(key)
        if fp not in _groq_checked:
            _groq_checked[fp] = _test_groq(key)
        groq = _groq_checked[fp]
    gemini = "ok" if os.getenv("GEMINI_API_KEY") else "no key"
    ollama = "ok" if _ollama_up() else "down"
    active = "groq" if groq == "ok" else "gemini" if gemini == "ok" else "ollama" if ollama == "ok" else None
    return {"groq": groq, "gemini": gemini, "ollama": ollama, "active": active}


def llm_models() -> dict:
    return {"groq_model": os.getenv("GROQ_MODEL", GROQ_MODELS[0]),
            "ollama_model": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434")}


def _write_env(updates: dict) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    lines = [ln for ln in lines if ln.split("=", 1)[0].strip() not in updates]
    lines += [f"{k}={v}" for k, v in updates.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_api_key(key: str, remember: bool = False) -> dict:
    """Use this Groq key in this process; write it to .env (git-ignored) only if remember=True."""
    key = key.strip()
    os.environ["GROQ_API_KEY"] = key
    _groq_checked[_fingerprint(key)] = _test_groq(key)
    if remember:
        _write_env({"GROQ_API_KEY": key})
    return llm_status()


def set_groq_model(model: str, remember: bool = False) -> None:
    os.environ["GROQ_MODEL"] = model
    if remember:
        _write_env({"GROQ_MODEL": model})


def system_status() -> dict:
    """SystemStatus: what is built, and the command that builds what is missing."""
    modules = {f"src/{m}.py": (ROOT / "src" / f"{m}.py").exists()
               for m in ("text", "classify", "rules", "retrieve", "llm", "resolve", "decide", "pipeline", "store")}
    return {"model_file": MODEL_PATH.exists(), "search_index": INDEX_PATH.exists(),
            "modules": modules, "build_commands": BUILD_COMMANDS}
