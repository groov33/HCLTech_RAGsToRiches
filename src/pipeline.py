"""The whole flow for one ticket, in order. This is the file to read first.

    from src.pipeline import analyze_ticket, ask_kb
    result = analyze_ticket({"description": "...", "service": "VPN", "environment": "Production",
                             "who_affected": "Just me", "user_category": "Network",
                             "user_subcategory": "VPN problem"})
    answer = ask_kb("how do I reset my password?")      # KB Assistant (employees)

    python -m src.pipeline          # runs one demo ticket and prints the result

Steps (numbers match Docs/RAG_PLAN.md):
  1 clean       hype out, completeness check                       src/text.py
  2 tickets     similar past tickets + their vote (independent)    src/retrieve.py
  3 classify    ML labels, using the vote as a second opinion      src/classify.py
  4 kb          role-filtered KB search, nudged by the labels      src/retrieve.py
  5 fix         LLM writes steps from KB only, each cited          src/resolve.py + src/llm.py
  6 check       citation check (inside write_fix)                  src/resolve.py
  7 decide      rules -> RECOMMEND / REVIEW / ESCALATE / NEED_INFO  src/decide.py
"""
import time
from functools import lru_cache

from src.classify import TicketClassifier
from src.decide import KB_FLOOR, decide
from src.llm import LLMUnavailable
from src.resolve import write_fix
from src.retrieve import Retriever
from src.text import clean_description, is_too_vague


@lru_cache(maxsize=1)
def _classifier() -> TicketClassifier:      # loaded once, reused for every ticket
    return TicketClassifier.load()


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever.load()


class _Trace:
    """Records how long each step took, for the step-by-step view in the app."""

    def __init__(self):
        self.steps, self._t = [], time.perf_counter()

    def done(self, name: str, note: str = ""):
        now = time.perf_counter()
        self.steps.append({"step": name, "ms": round(1000 * (now - self._t)), "note": note})
        self._t = now


def analyze_ticket(ticket: dict, role: str = "analyst", use_llm: bool = True) -> dict:
    trace = _Trace()

    # 1 clean
    text = clean_description(ticket["description"])
    too_vague = is_too_vague(text)
    trace.done("clean", "too vague" if too_vague else "")

    # 2 similar tickets: uses only the user's service, so the vote is independent of the ML
    similar = _retriever().search_tickets(text, service=ticket.get("service"))
    trace.done("similar tickets", f"vote: {similar['vote_category']}")

    # 3 classify (+ priority rules inside)
    labels = _classifier().predict(ticket, similar_vote=similar["vote_category"])
    trace.done("classify", f"{labels['subcategory']} · {labels['priority']}")

    # 4 KB search: access filter first, predicted subcategory only as a boost
    kb = _retriever().search_kb(text, role=role, service=ticket.get("service"),
                                subcategory=labels["subcategory"],
                                sub_prob=labels["confidence"]["subcategory"])
    trace.done("kb search", f"best match {kb['kb_best']:.0%}")

    # 5 + 6 write the fix and check citations (skip the LLM if nothing can fit anyway)
    fix, llm_error = None, None
    if not use_llm:
        llm_error = "LLM switched off"
    elif kb["kb_best"] < KB_FLOOR:
        fix = {"paths": [], "steps_written": 0, "steps_kept": 0, "dropped": [], "citation_validity": 0.0,
               "insufficient_evidence": True, "clarifying_questions": [], "llm_used": None}
    else:
        try:
            fix = write_fix(text, {"category": labels["category"], "subcategory": labels["subcategory"],
                                   "service": ticket.get("service"), "environment": ticket.get("environment")},
                            kb["hits"], similar["hits"], role=role)
        except LLMUnavailable as e:
            llm_error = str(e)
    trace.done("write + check fix", (fix["llm_used"] or "no LLM needed") if fix else "LLM unavailable")

    # 7 decide
    outcome = decide(labels, kb, fix, too_vague, llm_error)
    trace.done("decide", outcome["decision"])

    return {"input": ticket, "role": role, "clean_text": text, "labels": labels,
            "similar_tickets": similar, "kb": kb, "fix": fix, "outcome": outcome, "trace": trace.steps}


def ask_kb(question: str) -> dict:
    """KB Assistant: employees get public articles and self-help steps only."""
    text = clean_description(question)
    kb = _retriever().search_kb(text, role="employee")
    if kb["kb_best"] < KB_FLOOR or is_too_vague(text):
        return {"answer": None, "message": "Not in the knowledge base. Please raise a ticket.", "kb": kb}
    try:
        fix = write_fix(text, {}, kb["hits"], [], role="employee")
    except LLMUnavailable:
        return {"answer": None, "message": "Assistant unavailable. Please raise a ticket.", "kb": kb}
    if fix["insufficient_evidence"]:
        return {"answer": None, "message": "Not in the knowledge base. Please raise a ticket.", "kb": kb}
    return {"answer": fix, "message": "", "kb": kb}


def _print(result: dict):
    lab, out, fix = result["labels"], result["outcome"], result["fix"]
    print(f"\n{out['decision']}  (confidence {out['confidence']:.0%})")
    for r in out["reasons"]:
        print(f"  - {r}")
    print(f"\nLabels: {lab['category']} > {lab['subcategory']} · {lab['symptom_type']} · {lab['team']}")
    print(f"Priority: {lab['priority_reason']}")
    print("\nSimilar tickets:")
    for t in result["similar_tickets"]["hits"]:
        print(f"  {t['ticket_id']} [{t['subcategory']}] {t['why_matched']}")
    print("\nKB articles:")
    for a in result["kb"]["hits"]:
        print(f"  {a['kb_id']} {a['title']}  ({a['why_matched']})")
    if fix:
        print(f"\nFix by {fix['llm_used']}: {fix['steps_kept']}/{fix['steps_written']} steps passed the citation check")
        for p in fix["paths"]:
            print(f"  {p['kb_id']}: {p['why_it_fits']}")
            for i, s in enumerate(p["steps"], 1):
                print(f"    {i}. {s['text']}  {s['cites']}")
        for d in fix["dropped"]:
            print(f"  dropped: {d}")
    print("\nTrace: " + " -> ".join(f"{s['step']} {s['ms']}ms" for s in result["trace"]))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    _print(analyze_ticket({   # INC-00156 from Docs/PROJECT_OVERVIEW.md: hype + wrong user category, P2
        "description": "I'm getting heat from above. Please pick this up immediately. The main account was "
                       "locked when an old desktop retried a saved password overnight. The desktop is off now "
                       "but I still can't log in.",
        "service": "Company Login", "environment": "Production", "who_affected": "Just me",
        "user_category": "Device & Software", "user_subcategory": "Computer problem"}))
