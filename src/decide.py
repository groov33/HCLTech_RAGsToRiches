"""Final outcome: plain rules, first match wins. No LLM here.

Confidence = plain average of three 0-1 numbers (no weights to tune or defend):
  * category_score     how sure the classifier is (model + ticket vote + user, from classify.py)
  * kb_best            how close in meaning the best KB article is to the ticket
  * citation_validity  share of fix steps that passed the citation check

| # | If                                                         | Then        |
|---|------------------------------------------------------------|-------------|
| 0 | no LLM reachable                                           | ESCALATE    |
| 1 | ticket too vague (or LLM only asked questions)             | NEED_INFO   |
| 2 | no KB article fits -> knowledge gap                        | ESCALATE    |
| 3 | priority P1 or P2                                          | ESCALATE    |
| 4 | classifier flags, articles conflict, sources disagree,     | REVIEW      |
|   | some steps dropped, or confidence < 0.6                    |             |
| 5 | otherwise                                                  | RECOMMEND   |
"""
KB_FLOOR = 0.20         # below this the best article is clearly unrelated (measured: 5th percentile 0.19)
MIN_CONFIDENCE = 0.60


def decide(labels: dict, kb: dict, fix: dict | None, too_vague: bool, llm_error: str | None = None) -> dict:
    """labels = classifier output, kb = Retriever.search_kb output, fix = write_fix output (None if LLM failed)."""
    validity = fix["citation_validity"] if fix else 0.0
    confidence = round((labels["confidence"]["category_score"] + kb["kb_best"] + validity) / 3, 3)

    def out(decision, *reasons):
        return {"decision": decision, "reasons": list(reasons), "confidence": confidence,
                "knowledge_gap": decision == "ESCALATE" and any("knowledge gap" in r for r in reasons)}

    team = labels["team"]
    if fix is None:
        return out("ESCALATE", f"LLM unavailable, handing to {team} with the evidence found ({llm_error})")
    if too_vague or (fix["clarifying_questions"] and not fix["paths"]):
        return out("NEED_INFO", "not enough detail to act on; ask the user the questions shown")
    if kb["kb_best"] < KB_FLOOR or fix["insufficient_evidence"]:
        return out("ESCALATE", f"knowledge gap: no KB article fits this ticket, handing to {team}")
    if labels["priority"] in ("P1", "P2"):
        return out("ESCALATE", f"{labels['priority']}: a {team} engineer owns it; the cited fix is attached")

    review = list(labels.get("review_reasons", []))
    top = kb["hits"][0] if kb["hits"] else None
    if kb["conflict"]:
        review.append("the top two articles are about different problems")
    if top and top["subcategory"] != labels["subcategory"]:
        review.append(f"classifier says '{labels['subcategory']}', best article is about '{top['subcategory']}'")
    if fix["dropped"]:
        review.append(f"{len(fix['dropped'])} fix step(s) failed the citation check and were removed")
    if confidence < MIN_CONFIDENCE:
        review.append(f"low confidence ({confidence:.0%})")
    if review:
        return out("REVIEW", *review)
    return out("RECOMMEND", f"classifier, similar tickets and KB agree (confidence {confidence:.0%})")
