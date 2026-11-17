"""Final outcome: plain rules, first match wins. No LLM here.  ->  contracts.Decision

Confidence = plain average of three 0-1 numbers (no weights to tune or defend):
  * category_score     how sure the classifier is (model + ticket vote + user, from classify.py)
  * kb best_score      how close in meaning the best KB article is to the ticket
  * citation_validity  share of fix steps that passed the citation check

| # | If                                                         | Then        |
|---|------------------------------------------------------------|-------------|
| 1 | ticket too vague (or the LLM only asked questions)         | NEED_INFO   |
| 2 | no KB article fits -> knowledge gap                        | ESCALATE    |
| 2b| LLM off or unreachable (no fix could be written)           | ESCALATE    |
| 3 | priority P1 or P2                                          | ESCALATE    |
| 4 | classifier flags, articles conflict, sources disagree,     | REVIEW      |
|   | some steps dropped, or confidence < 0.6                    |             |
| 5 | otherwise                                                  | RECOMMEND   |
"""
MIN_CONFIDENCE = 0.60
DEFAULT_QUESTIONS = ["Which application, device or service is affected?",
                     "What exactly happens, and is there an error message?"]


def decide(labels: dict, kb: dict, fix: dict | None, too_vague: bool,
           knowledge_gap: bool, llm_error: str | None = None) -> dict:
    """labels = Classification, kb = KBSearchResult, fix = Fix (None if the LLM failed or wasn't needed)."""
    validity = fix["citation_validity"] if fix else 0.0
    confidence = round((labels["confidence"]["category_score"] + kb["best_score"] + validity) / 3, 3)
    team = labels["team"]

    def out(outcome, reasons, questions=(), escalate=False):
        return {"outcome": outcome, "confidence": confidence, "reasons": list(reasons),
                "questions": list(questions), "escalate_to": team if escalate else None}

    # Vague and knowledge-gap checks come first: neither needs the LLM, so "LLM off" must not hide them.
    if too_vague or (fix and fix["clarifying_questions"] and not fix["paths"]):
        questions = (fix and fix["clarifying_questions"]) or DEFAULT_QUESTIONS
        return out("NEED_INFO", ["not enough detail to act on; ask the user the questions below"], questions)
    if knowledge_gap:
        why = kb.get("gap_reason") or "no KB article fits this ticket"
        return out("ESCALATE", [f"knowledge gap: {why}, handing to {team}"], escalate=True)
    if llm_error:
        return out("ESCALATE", [f"no fix written ({llm_error[:80]}): handing to {team} with the evidence found"],
                   escalate=True)
    if not fix:
        why = kb.get("gap_reason") or "no KB article fits this ticket"
        return out("ESCALATE", [f"knowledge gap: {why}, handing to {team}"], escalate=True)
    if labels["priority"] in ("P1", "P2"):
        return out("ESCALATE", [f"{labels['priority']}: a {team} engineer owns it; the cited fix is attached"],
                   escalate=True)

    review = list(labels.get("review_reasons", []))
    top = kb["articles"][0] if kb["articles"] else None
    if kb["conflict"]:
        review.append("the top two articles are about different problems")
    if top and top["subcategory"] != labels["subcategory"]:
        review.append(f"classifier says '{labels['subcategory']}', best article is about '{top['subcategory']}'")
    if fix["dropped_steps"]:
        review.append(f"{fix['dropped_steps']} fix step(s) failed the citation check and were removed")
    if confidence < MIN_CONFIDENCE:
        review.append(f"low confidence ({confidence:.0%})")
    if review:
        return out("REVIEW", review)
    return out("RECOMMEND", [f"classifier, similar tickets and KB agree (confidence {confidence:.0%})"])
