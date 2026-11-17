"""Write a fix from KB articles, then check every citation.

    from src.resolve import write_fix
    fix = write_fix(ticket_text, labels, kb_hits, ticket_hits, role="analyst")

1. PROMPT  the LLM sees: the cleaned ticket, predicted labels, the top KB articles
           with numbered step IDs, and similar past tickets marked CONTEXT ONLY
           (tickets have no fixes, so they can't be cited).
2. ANSWER  JSON: paths -> steps, each step citing step IDs like "KB-020/support/1".
3. CHECK   (code, not trust) a step is kept only if
             a) every ID it cites is one we actually gave the LLM, and
             b) its wording still matches the cited source (rapidfuzz >= 70).
           citation_validity = steps kept / steps written.

So "no unsupported conclusions" (FR-05) is enforced by code, not hoped for.
"""
from rapidfuzz import fuzz

from src.kb import access_for, article_steps, load_articles
from src.llm import ask_json

MIN_MATCH = 70   # 0-100 wording overlap between a written step and its cited source

SYSTEM = """You are an IT support assistant. Recommend a fix for the ticket using ONLY the KB articles given.
Rules:
- Every step must cite at least one step ID from the articles, e.g. "KB-020/support/1".
- Keep each step's wording close to the cited step. You may adapt it to the ticket, but add nothing new.
- Similar past tickets are context only. Never cite them.
- If no article really fits this ticket, set "insufficient_evidence": true and give no paths.
- If the ticket is too vague to act on, add 1-2 short questions to "clarifying_questions".
Answer with JSON only, in this shape:
{"paths": [{"kb_id": "KB-000", "why_it_fits": "one sentence linking the ticket to the article",
            "steps": [{"text": "...", "cites": ["KB-000/support/1"]}]}],
 "insufficient_evidence": false,
 "clarifying_questions": []}"""


def build_prompt(ticket_text: str, labels: dict, kb_hits: list[dict], ticket_hits: list[dict],
                 step_types) -> tuple[str, dict]:
    """Return (prompt, allowed step ID -> step) so the checker knows what was really shown."""
    articles = load_articles()
    allowed, blocks = {}, []
    for hit in kb_hits:
        a = articles[hit["kb_id"]]
        steps = article_steps(a, step_types)
        allowed.update({s["id"]: s for s in steps})
        lines = [f"ARTICLE {a['kb_id']}: {a['title']}",
                 f"  Symptoms: {' | '.join(a['symptoms'])}",
                 f"  Cause: {a['cause']}",
                 "  Steps:"] + [f"    [{s['id']}] {s['text']}" for s in steps]
        lines.append(f"  Escalate when: {a['escalate_when']}")
        blocks.append("\n".join(lines))
    similar = "\n".join(f"- {t['ticket_id']} ({t['subcategory']}): {t['description']}"
                        for t in ticket_hits) or "- none"
    label_txt = ", ".join(f"{k}: {v}" for k, v in labels.items() if v)
    prompt = (f"TICKET: {ticket_text}\n{label_txt}\n\n"
              f"KB ARTICLES:\n" + ("\n\n".join(blocks) or "none") +
              f"\n\nSIMILAR PAST TICKETS (context only, do not cite):\n{similar}")
    return prompt, allowed


def check_citations(paths: list[dict], allowed: dict) -> tuple[list[dict], int, int, list[str]]:
    """Keep only steps whose citations exist AND whose wording matches the source."""
    kept_paths, written, kept, dropped = [], 0, 0, []
    for path in paths or []:
        good_steps = []
        for step in path.get("steps") or []:
            written += 1
            text, cites = str(step.get("text", "")), [str(c) for c in step.get("cites") or []]
            unknown = [c for c in cites if c not in allowed]
            if not cites or unknown:
                dropped.append(f"'{text[:60]}' cites {unknown or 'nothing'}")
                continue
            best = max(fuzz.token_set_ratio(text, allowed[c]["text"]) for c in cites)
            if best < MIN_MATCH:
                dropped.append(f"'{text[:60]}' doesn't match its source ({best:.0f}/100)")
                continue
            kept += 1
            good_steps.append({"text": text, "cites": cites, "match": round(best),
                               "source": [{"id": c, "text": allowed[c]["text"]} for c in cites]})
        if good_steps:
            kept_paths.append({"kb_id": path.get("kb_id"), "why_it_fits": path.get("why_it_fits", ""),
                               "steps": good_steps})
    return kept_paths, written, kept, dropped


def write_fix(ticket_text: str, labels: dict, kb_hits: list[dict], ticket_hits: list[dict],
              role: str = "analyst") -> dict:
    """May raise src.llm.LLMUnavailable (the caller escalates)."""
    prompt, allowed = build_prompt(ticket_text, labels, kb_hits, ticket_hits, access_for(role)["step_types"])
    answer, llm_used = ask_json(SYSTEM, prompt)
    paths, written, kept, dropped = check_citations(answer.get("paths"), allowed)
    return {
        "paths": paths,
        "steps_written": written,
        "steps_kept": kept,
        "dropped": dropped,
        "citation_validity": round(kept / written, 3) if written else 0.0,
        "insufficient_evidence": bool(answer.get("insufficient_evidence")) or not paths,
        "clarifying_questions": [str(q) for q in answer.get("clarifying_questions") or []][:2],
        "llm_used": llm_used,
    }
