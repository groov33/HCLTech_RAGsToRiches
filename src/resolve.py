"""Write a fix from KB articles, then check every citation.

    from src.resolve import write_fix
    fix, insufficient = write_fix(clean_text, labels, kb["articles"], similar["tickets"])

1. PROMPT  the LLM sees: the cleaned, PII-masked ticket, predicted labels, the top
           KB articles with numbered step IDs (already filtered by role), and
           similar past tickets marked CONTEXT ONLY (tickets have no fixes).
2. ANSWER  JSON: paths -> steps, each step citing step IDs like "KB-020/support/1".
3. CHECK   (code, not trust) a step is kept only if
             a) every ID it cites is one we actually gave the LLM, and
             b) its wording still matches the cited source (rapidfuzz >= 70).
           citation_validity = steps kept / steps written.

So "no unsupported conclusions" (FR-05) is enforced by code, not hoped for.
"""
from rapidfuzz import fuzz

from src.llm import ask_json

MIN_MATCH = 70   # 0-100 wording overlap between a written step and its cited source

SYSTEM = """You are an IT support assistant. Recommend a fix for the ticket using ONLY the KB articles given.
Rules:
- Use only the article(s) that really fit; usually one is enough. One path per article, holding all its steps in order.
- Every step must cite at least one step ID from the articles, e.g. "KB-020/support/1".
- Keep each step's wording close to the cited step. You may adapt it to the ticket, but add nothing new.
- Similar past tickets are context only. Never cite them.
- An article fits only if it is about the same system or device as the ticket. A similar-sounding problem on a different system does not fit.
- If no article really fits this ticket, set "insufficient_evidence": true and give no paths.
- If the ticket is too vague to act on, add 1-2 short questions to "clarifying_questions".
Answer with JSON only, in this shape:
{"paths": [{"kb_id": "KB-000", "why_it_fits": "one sentence linking the ticket to the article",
            "steps": [{"text": "...", "cites": ["KB-000/support/1"]}]}],
 "insufficient_evidence": false,
 "clarifying_questions": []}"""


def build_prompt(ticket_text: str, labels: dict, articles: list[dict], tickets: list[dict]) -> str:
    blocks = []
    for a in articles:
        lines = [f"ARTICLE {a['kb_id']}: {a['title']}", "  Steps:"]
        lines += [f"    [{s['step_id']}] {s['text']}" for s in a["steps"]]
        lines.append(f"  Escalate when: {a['escalate_when']}")
        blocks.append("\n".join(lines))
    similar = "\n".join(f"- {t['ticket_id']} ({t['subcategory']}): {t['excerpt']}" for t in tickets) or "- none"
    label_txt = ", ".join(f"{k}: {v}" for k, v in labels.items() if v)
    return (f"TICKET: {ticket_text}\n{label_txt}\n\n"
            f"KB ARTICLES:\n" + ("\n\n".join(blocks) or "none") +
            f"\n\nSIMILAR PAST TICKETS (context only, do not cite):\n{similar}")


def check_citations(paths, allowed: dict, titles: dict) -> tuple[list[dict], int, list[str]]:
    """Keep only steps whose citations exist AND whose wording matches the source.

    allowed = step_id -> source text (only what the LLM was shown).
    Returns (paths that still have steps, steps written, reasons for each dropped step).
    """
    kept_paths, written, dropped = [], 0, []
    for path in paths if isinstance(paths, list) else []:
        if not isinstance(path, dict):             # LLM broke the JSON shape: count it as a failed step
            written += 1
            dropped.append(f"malformed path {str(path)[:60]!r}")
            continue
        good = []
        for step in path.get("steps") if isinstance(path.get("steps"), list) else []:
            written += 1
            if not isinstance(step, dict):
                dropped.append(f"malformed step {str(step)[:60]!r}")
                continue
            text, cites = str(step.get("text", "")), [str(c) for c in step.get("cites") or []]
            unknown = [c for c in cites if c not in allowed]
            if not cites or unknown:
                dropped.append(f"'{text[:60]}' cites {unknown or 'nothing'}")
                continue
            match = max(fuzz.token_set_ratio(text, allowed[c]) for c in cites)
            if match < MIN_MATCH:
                dropped.append(f"'{text[:60]}' doesn't match its source ({match:.0f}/100)")
                continue
            good.append({"text": text, "cites": cites,
                         "source_quote": " | ".join(allowed[c] for c in cites)})
        if good:
            kb_id = str(path.get("kb_id") or good[0]["cites"][0].split("/")[0])
            kept_paths.append({"kb_id": kb_id, "title": titles.get(kb_id, ""),
                               "why_it_fits": str(path.get("why_it_fits", "")), "steps": good})
    return kept_paths, written, dropped


def write_fix(ticket_text: str, labels: dict, articles: list[dict], tickets: list[dict]) -> tuple[dict, bool]:
    """Return (contracts.Fix, insufficient_evidence). May raise src.llm.LLMUnavailable."""
    answer, llm_used = ask_json(SYSTEM, build_prompt(ticket_text, labels, articles, tickets))
    allowed = {s["step_id"]: s["text"] for a in articles for s in a["steps"]}
    paths, written, dropped = check_citations(answer.get("paths"), allowed,
                                              {a["kb_id"]: a["title"] for a in articles})
    kept = sum(len(p["steps"]) for p in paths)
    fix = {
        "paths": paths,
        "citation_validity": round(kept / written, 3) if written else 0.0,
        "dropped_steps": len(dropped),
        "dropped_reasons": dropped,               # extra detail for the trace / evaluation
        "llm": llm_used.split(":")[0],            # contract wants "groq" | "gemini" | "ollama"
        "llm_model": llm_used,
        "clarifying_questions": [str(q) for q in answer.get("clarifying_questions") or []][:2],
    }
    return fix, bool(answer.get("insufficient_evidence")) or not paths
