"""SHOWCASE ONLY: fill the audit log with fake resolved tickets so the MTTR page has something to show.

We have no real resolution history, so these records are invented. Every one is marked:
analysis_id starts with "DEMO-", analyst = "Simulated demo data".

    python -m build.seed_mttr_demo           # add 60 fake resolved tickets
    python -m build.seed_mttr_demo --clear   # remove them again
"""
import argparse
import json
import random
from datetime import datetime, timedelta

from src import store

N = 60
ANALYST = "Simulated demo data"
# Fake "time to resolve with the assistant", in minutes (min, max) per priority.
# Compare with the simulated manual baseline in app/backend.py: P1 4 h, P2 8 h, P3 1 day, P4 2 days.
ASSISTED_MIN = {"P1": (60, 150), "P2": (120, 300), "P3": (240, 720), "P4": (480, 1440)}


def clear() -> None:
    with store._db() as con:
        con.execute("DELETE FROM evidence WHERE analysis_id LIKE 'DEMO-%'")
        n = con.execute("DELETE FROM analyses WHERE analysis_id LIKE 'DEMO-%'").rowcount
    print(f"Removed {n} demo records.")


def seed() -> None:
    random.seed(7)                                   # same fake data every run
    tickets = [json.loads(line) for line in open("data/resolveiq_tickets.jsonl", encoding="utf-8")]
    start = datetime.now() - timedelta(days=30)
    for i, t in enumerate(random.sample(tickets, N), 1):
        created = start + timedelta(minutes=random.randint(0, 29 * 24 * 60))
        recommended = created + timedelta(seconds=random.randint(3, 20))
        resolved = created + timedelta(minutes=random.randint(*ASSISTED_MIN[t["priority"]]))
        store.save_analysis({
            "analysis_id": f"DEMO-{i:04d}", "analyst": ANALYST, "role": "support",
            "ticket": {k: t[k] for k in ("description", "service", "environment", "who_affected")},
            "classification": {"category": t["category"], "subcategory": t["subcategory"],
                               "priority": t["priority"], "confidence": {"category_score": 1.0}},
            "decision": {"outcome": "RECOMMEND", "confidence": 1.0, "reasons": ["simulated demo record"],
                         "questions": [], "escalate_to": None},
            "similar": None, "kb": None, "fix": None, "tiebreak": None,
            "timestamps": {"created_at": created.isoformat(timespec="seconds"),
                           "recommended_at": recommended.isoformat(timespec="seconds"),
                           "resolved_at": resolved.isoformat(timespec="seconds")},
        })
    print(f"Added {N} demo records. Open Admin > MTTR in the app.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true", help="remove the demo records")
    args = ap.parse_args()
    clear()                                          # always start clean, so re-running never doubles up
    if not args.clear:
        seed()
