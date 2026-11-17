"""The whole flow for one ticket, in order. This is the file to read first.

    from src.pipeline import analyze_ticket, ask_kb
    result = analyze_ticket(ticket, role="support", analyst="Asha")   # -> contracts.AnalysisResult
    answer = ask_kb("how do I reset my password?")                     # -> contracts.KBAnswer

    python -m src.pipeline          # runs demo ticket INC-00347 (held out) + hype and prints the result

Steps (numbers = Docs/PROJECT_OVERVIEW.md §4):
  2 clean       hide PII, drop hype, completeness check            src/text.py
  4 similar     similar past tickets + their vote (independent)    src/retrieve.py
  3 classify    ML labels using the vote, + 5 score, 6 priority    src/classify.py
  7 kb          role-filtered KB search, nudged by the labels      src/retrieve.py
  8 fix         LLM writes steps from KB only + citation check     src/resolve.py, src/llm.py
  9 decide      rules -> RECOMMEND / REVIEW / ESCALATE / NEED_INFO  src/decide.py
"""
import secrets
import time
from datetime import datetime
from functools import lru_cache

from src.classify import TicketClassifier
from src.contracts import CONTRACT_VERSION
from src.decide import decide
from src.llm import LLMUnavailable
from src.resolve import write_fix
from src.retrieve import Retriever
from src.text import clean_description, has_hype, is_too_vague, mask_pii


@lru_cache(maxsize=1)
def _classifier() -> TicketClassifier:      # loaded once, reused for every ticket
    return TicketClassifier.load()


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever.load()


class _Trace:
    """How long each step took + its key output, for the step-by-step view in the app."""

    def __init__(self):
        self.steps, self._t = [], time.perf_counter()

    def done(self, step: str, name: str, detail: str = "", status: str = "done"):
        now = time.perf_counter()
        self.steps.append({"step": step, "name": name, "ms": round(1000 * (now - self._t), 1),
                           "detail": detail, "status": status})
        self._t = now


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def analyze_ticket(ticket: dict, role: str = "support", analyst: str = "", use_llm: bool = True) -> dict:
    created_at, trace = _now(), _Trace()

    # 2 clean: PII hidden first, so nothing below (search, LLM, UI) ever sees it
    masked = mask_pii(ticket["description"])
    text = clean_description(masked)
    cleaned = {"masked_description": masked, "clean_text": text,
               "hype_detected": has_hype(masked), "too_vague": is_too_vague(text)}
    trace.done("2", "Clean text", "too vague" if cleaned["too_vague"] else f"{len(text.split())} words")
    safe_ticket = {**ticket, "description": masked}

    # 4 similar tickets: only the user's own service is used, so the vote is independent of the ML
    similar = _retriever().search_tickets(text, service=ticket.get("service"))
    vote = similar["vote"]
    trace.done("4", "Similar tickets", f"vote {vote['category']} ({vote['agree_count']}/{vote['of']})" if vote else "none")

    # 3 + 5 + 6 classify, combined score, priority rules
    labels = _classifier().predict(safe_ticket, similar_vote=vote["category"] if vote else None)
    trace.done("3", "Classify + priority",
               f"{labels['subcategory']} {labels['confidence']['category_score']:.2f} · {labels['priority']}")

    # 7 KB search: access filter first, predicted subcategory only as a boost
    kb = _retriever().search_kb(text, role=role, service=ticket.get("service"),
                                subcategory=labels["subcategory"],
                                sub_prob=labels["confidence"]["subcategory"])
    trace.done("7", "Find KB articles", f"best match {kb['best_score']:.0%}")

    # 7b two problems in one ticket? Each clause is searched on its own; different strong matches -> REVIEW
    problems = _retriever().distinct_problems(text, role=role)
    if len(problems) > 1:
        labels["review_reasons"].append(
            "may be two problems in one ticket (" + " / ".join(f"'{p['clause']}' -> {p['subcategory']}"
                                                              for p in problems) + "): one fix may miss the other")
        labels["needs_review"] = True
    trace.done("7b", "Two-problem check", f"{len(problems)} distinct problem(s)")

    # 8 write the fix + check citations (no LLM call when the ticket is too vague or nothing can fit)
    fix, llm_error, insufficient = None, None, kb["knowledge_gap"]
    if not use_llm:
        llm_error = "LLM switched off"
    elif not insufficient and not cleaned["too_vague"]:
        try:
            fix, insufficient = write_fix(
                text, {"category": labels["category"], "subcategory": labels["subcategory"],
                       "service": ticket.get("service"), "environment": ticket.get("environment")},
                kb["articles"], similar["tickets"])
        except LLMUnavailable as e:
            llm_error = str(e)
    if fix and insufficient and not fix["clarifying_questions"]:
        kb["knowledge_gap"], fix = True, None        # contract: no fix object for a knowledge gap
        kb["gap_reason"] = "the LLM found no article that really fits"
    detail = (f"{fix['llm_model']}: {sum(len(p['steps']) for p in fix['paths'])} steps kept, "
              f"{fix['dropped_steps']} dropped" if fix else
              "LLM unavailable" if llm_error else
              "skipped: too vague" if cleaned["too_vague"] else "skipped: knowledge gap")
    trace.done("8", "Write fix + check citations", detail, "done" if fix else "failed" if llm_error else "skipped")

    # 9 decide
    decision = decide(labels, kb, fix, cleaned["too_vague"], kb["knowledge_gap"], llm_error)
    trace.done("9", "Decide", decision["outcome"])

    return {
        "contract_version": CONTRACT_VERSION,
        "analysis_id": f"AN-{datetime.now():%Y%m%d}-{secrets.randbelow(10000):04d}",
        "analyst": analyst, "role": role, "ticket": safe_ticket, "cleaned": cleaned,
        "similar": similar, "classification": labels,
        "tiebreak": None,                              # LLM tiebreak not built yet
        "kb": kb, "fix": fix, "decision": decision, "trace": trace.steps,
        "timestamps": {"created_at": created_at, "recommended_at": _now(), "resolved_at": None},
        "missing_parts": ["store"],                    # audit log (src/store.py) not built yet
    }


def ask_kb(question: str, role: str = "employee") -> dict:
    """KB Assistant -> contracts.KBAnswer. Employees: public articles, self-help steps only."""
    text = clean_description(mask_pii(question))
    kb = _retriever().search_kb(text, role=role)
    answer = {"question": question, "answered": False, "steps": [], "sources": kb["articles"], "llm": None}
    if kb["knowledge_gap"] or is_too_vague(text):
        return answer
    try:
        fix, insufficient = write_fix(text, {}, kb["articles"], [])
    except LLMUnavailable:
        return answer
    answer["llm"] = fix["llm"]
    if not insufficient:
        answer["answered"] = True
        answer["steps"] = [s for p in fix["paths"] for s in p["steps"]]
    return answer


def _print(r: dict):
    lab, d, fix = r["classification"], r["decision"], r["fix"]
    print(f"\n{d['outcome']}  (confidence {d['confidence']:.0%})")
    for x in d["reasons"] + d["questions"]:
        print(f"  - {x}")
    print(f"\nLabels: {lab['category']} > {lab['subcategory']} · {lab['symptom_type']} · {lab['team']}")
    print(f"Priority: {lab['priority_reason']}")
    print("\nSimilar tickets:")
    for t in r["similar"]["tickets"]:
        print(f"  {t['ticket_id']} [{t['subcategory']}] {' · '.join(t['why_matched'])}"
              f"{'  DUPLICATE?' if t['is_duplicate'] else ''}")
    print("\nKB articles:")
    for a in r["kb"]["articles"]:
        print(f"  {a['kb_id']} {a['title']}  ({' · '.join(a['why_matched'])})")
    if fix:
        print(f"\nFix by {fix['llm_model']}: citation validity {fix['citation_validity']:.0%}")
        for p in fix["paths"]:
            print(f"  {p['kb_id']} {p['title']}: {p['why_it_fits']}")
            for i, s in enumerate(p["steps"], 1):
                print(f"    {i}. {s['text']}  {s['cites']}")
        for x in fix["dropped_reasons"]:
            print(f"  dropped: {x}")
    print("\nTrace: " + " -> ".join(f"{s['step']} {s['name']} {s['ms']:.0f}ms" for s in r["trace"]))


if __name__ == "__main__":
    import sys

    from src.contracts import check_result
    sys.stdout.reconfigure(encoding="utf-8")
    # Held-out test ticket INC-00347 (never trained on or indexed) with one hype sentence added.
    # Shows: hype ignored, wrong user category corrected, P2 from facts, cited fix -> ESCALATE.
    result = analyze_ticket({
        "description": "I'm getting heat from above. Please pick this up immediately. My workng salary "
                       "application closes just after login. I can see the menu for a moment but can't open a run.",
        "service": "Payroll System", "environment": "Production", "who_affected": "Just me",
        "user_category": "Device & Software", "user_subcategory": "Install software"}, analyst="demo")
    _print(result)
    print("\nContract check:", check_result(result) or "OK")
