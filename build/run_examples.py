"""Run the real pipeline on the worked-example tickets in reports/EXAMPLES.md.

    python -m build.run_examples      # -> reports/examples_results.json (full AnalysisResult per ticket)

Six tickets, chosen so that every outcome appears at least once:
RECOMMEND, REVIEW, ESCALATE (priority), ESCALATE (knowledge gap) and NEED_INFO.
Needs an LLM route (GROQ_API_KEY / GEMINI_API_KEY in .env, or Ollama) for the fix-writing step.
"""
import json
import sys
from pathlib import Path

from src.pipeline import analyze_ticket

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "examples_results.json"
INPUT_COLS = ["description", "service", "environment", "who_affected", "user_category", "user_subcategory"]
LABEL_COLS = ["category", "subcategory", "symptom_type", "team", "priority"]
HYPE = "I'm getting heat from above. Please pick this up immediately."


def _probe(description: str, service: str, who: str) -> tuple[dict, None]:
    return {"description": description, "service": service, "environment": "Production", "who_affected": who,
            "user_category": None, "user_subcategory": None}, None


def cases() -> list[tuple[str, dict, dict | None]]:
    rows = {r["ticket_id"]: r for r in map(json.loads, open(ROOT / "data" / "resolveiq_tickets.jsonl", encoding="utf-8"))}

    def held_out(tid: str, hype: str = "") -> tuple[dict, dict]:
        r = rows[tid]
        ticket = {c: r[c] for c in INPUT_COLS}
        if hype:
            ticket["description"] = f"{hype} {ticket['description']}"
        return ticket, {c: r[c] for c in LABEL_COLS}

    return [
        ("INC-00073", *held_out("INC-00073")),
        ("INC-00040", *held_out("INC-00040")),
        ("INC-00347 + hype", *held_out("INC-00347", HYPE)),
        ("probe: hidden security", *_probe("My laptop got very slow after I opened an invoice attachment, and now a "
                                           "window says my files are encrypted and asks for payment.",
                                           "Laptop / Desktop", "Just me")),
        ("probe: knowledge gap", *_probe("Customers see the wrong prices on the company website product pages.",
                                         "Company Website", "Customers")),
        ("probe: too vague", *_probe("System not working, please help.", "Other / Not sure", "Just me")),
    ]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = []
    for name, ticket, truth in cases():
        res = analyze_ticket(ticket, role="support", analyst="examples")
        out.append({"name": name, "input": ticket, "truth": truth, "result": res})
        print(f"{name:24s} -> {res['decision']['outcome']:9s} {res['decision']['reasons'][0]}")
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"saved {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
