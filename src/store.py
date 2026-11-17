"""Audit log + feedback storage (FR-06, FR-08, FR-09).

    from src import store
    store.save_analysis(result)            # one row per AnalysisResult (already PII-masked)
    store.mark_resolved("AN-...")          # sets resolved_at -> feeds MTTR
    store.add_feedback(record)             # FeedbackRecord -> data/store/feedback.json

SQLite for analyses (one file, no server, queryable), a plain JSON list for
feedback (tiny, human-readable, easy for other scripts to read).
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

STORE_DIR = Path(__file__).resolve().parents[1] / "data" / "store"
DB_PATH = STORE_DIR / "resolveiq.db"
FEEDBACK_PATH = STORE_DIR / "feedback.json"
_lock = threading.Lock()          # Streamlit reruns can overlap; keep file writes one at a time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY, created_at TEXT, recommended_at TEXT, resolved_at TEXT,
    analyst TEXT, role TEXT, ticket_json TEXT, result_json TEXT,
    outcome TEXT, priority TEXT, category TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS evidence (
    analysis_id TEXT, source_type TEXT, source_id TEXT, score REAL, excerpt TEXT);
"""


def _db() -> sqlite3.Connection:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_analysis(result: dict) -> None:
    """Store one AnalysisResult and its evidence. The result must already be masked."""
    sim = (result.get("similar") or {}).get("tickets", [])
    arts = (result.get("kb") or {}).get("articles", [])
    evidence = ([(result["analysis_id"], "ticket", t["ticket_id"], t["score"], t["excerpt"][:300]) for t in sim]
                + [(result["analysis_id"], "kb", a["kb_id"], a["score"], a["title"]) for a in arts])
    ts, lab, dec = result["timestamps"], result["classification"], result["decision"]
    with _lock, _db() as con:
        con.execute("INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (result["analysis_id"], ts["created_at"], ts["recommended_at"], ts["resolved_at"],
                     result["analyst"], result["role"], json.dumps(result["ticket"]), json.dumps(result),
                     dec["outcome"], lab["priority"], lab["category"], dec["confidence"]))
        con.execute("DELETE FROM evidence WHERE analysis_id = ?", (result["analysis_id"],))
        con.executemany("INSERT INTO evidence VALUES (?,?,?,?,?)", evidence)


def mark_resolved(analysis_id: str) -> str | None:
    """Set resolved_at (in the column AND inside result_json). Returns the timestamp, or None if unknown id."""
    when = _now()
    with _lock, _db() as con:
        row = con.execute("SELECT result_json FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
        if not row:
            return None
        result = json.loads(row["result_json"])
        result["timestamps"]["resolved_at"] = when
        con.execute("UPDATE analyses SET resolved_at = ?, result_json = ? WHERE analysis_id = ?",
                    (when, json.dumps(result), analysis_id))
    return when


def list_analyses(outcome: list | None = None, priority: list | None = None,
                  analyst: str | None = None) -> list[dict]:
    """Full AnalysisResult dicts, newest first, optionally filtered."""
    sql, args = "SELECT result_json FROM analyses WHERE 1=1", []
    for col, values in (("outcome", outcome), ("priority", priority)):
        if values:
            sql += f" AND {col} IN ({','.join('?' * len(values))})"
            args += list(values)
    if analyst:
        sql += " AND analyst = ?"
        args.append(analyst)
    with _db() as con:
        rows = con.execute(sql + " ORDER BY created_at DESC", args).fetchall()
    return [json.loads(r["result_json"]) for r in rows]


def get_analysis(analysis_id: str) -> dict | None:
    with _db() as con:
        row = con.execute("SELECT result_json FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def add_feedback(record: dict) -> None:
    """Append a FeedbackRecord. Same analyst + analysis + target replaces the earlier verdict (control stays editable)."""
    with _lock:
        items = list_feedback()
        key = (record["analysis_id"], record["analyst"], record["target_type"], record["target_id"])
        items = [f for f in items if (f["analysis_id"], f["analyst"], f["target_type"], f["target_id"]) != key]
        items.append(record)
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        FEEDBACK_PATH.write_text(json.dumps(items, indent=1), encoding="utf-8")


def list_feedback(analyst: str | None = None) -> list[dict]:
    if not FEEDBACK_PATH.exists():
        return []
    items = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8") or "[]")
    return [f for f in items if analyst is None or f["analyst"] == analyst]
