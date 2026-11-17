"""Evaluation questions with expected answers, run through the same code the app uses.

    python -m build.run_eval_cases              # one pass -> reports/EVAL_CASES.md + reports/eval_cases_results.json
    python -m build.run_eval_cases --runs 3     # repeat: a case passes only if it passes every time (LLM stability)
    python -m build.run_eval_cases --only T01 K03

Cases live in data/eval_cases.json: the exact form input (paste it into the app to see the same
result) and an `expected` block. Only the fields listed in `expected` are checked.
`expected` always holds the RIGHT answer. Where the app is known to differ on one field, the case
also has `known_misses: {field: why}`: that field is still checked and reported in its own section,
but not counted as a failure (and you are told if it starts matching).

Same code path as the app:
  New ticket page  -> app.backend.analyze_ticket -> src.pipeline.analyze_ticket(ticket, role="support")
  KB Assistant     -> app.backend.ask_kb         -> src.pipeline.ask_kb(question, role="employee")
We call the src.pipeline functions directly so test runs are not written to the audit log
(they would otherwise show up on the Feedback and MTTR pages).
Needs an LLM route (GROQ_API_KEY / GEMINI_API_KEY in .env, or Ollama) for the fix-writing step.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.pipeline import analyze_ticket, ask_kb

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "eval_cases.json"
OUT_JSON = ROOT / "reports" / "eval_cases_results.json"
OUT_MD = ROOT / "reports" / "EVAL_CASES.md"


# ── what the app shows, as one flat dict per case ──────────────────────────────
def ticket_view(r: dict) -> dict:
    lab, d, kb, fix, sim = r["classification"], r["decision"], r["kb"], r["fix"], r["similar"]
    return {
        "outcome": d["outcome"], "category": lab["category"], "subcategory": lab["subcategory"],
        "symptom_type": lab["symptom_type"], "team": lab["team"], "priority": lab["priority"],
        "escalate_to": d["escalate_to"], "hype_detected": r["cleaned"]["hype_detected"],
        "user_agrees": lab["user_agrees"], "possible_security": lab["possible_security"],
        "knowledge_gap": kb["knowledge_gap"],
        "possible_duplicate": any(t["is_duplicate"] for t in sim["tickets"]),
        "top_similar": sim["tickets"][0]["ticket_id"] if sim["tickets"] else None,
        "top_kb": kb["articles"][0]["kb_id"] if kb["articles"] else None,
        "kb_top3": [a["kb_id"] for a in kb["articles"]],
        "fix_from": [p["kb_id"] for p in fix["paths"]] if fix else None,
        "reasons": " | ".join(d["reasons"]), "questions": d["questions"],
        "priority_reason": lab["priority_reason"],
        "masked_description": r["cleaned"]["masked_description"],
        # context only (not checked unless listed in expected)
        "confidence": d["confidence"], "dropped_steps": fix["dropped_steps"] if fix else None,
        "llm": fix["llm_model"] if fix else None,
    }


def kb_view(a: dict) -> dict:
    cites = [c for s in a["steps"] for c in s["cites"]]
    return {
        "answered": a["answered"],
        "top_source": a["sources"][0]["kb_id"] if a["sources"] else None,
        "answer_from": sorted({c.split("/")[0] for c in cites}) or None,
        "source_ids": [s["kb_id"] for s in a["sources"]],
        "cites_only_self_help": all("/self/" in c for c in cites),
        "only_public_sources": all(s["access_level"] == "public" for s in a["sources"]),
        "steps": len(a["steps"]), "llm": a["llm"],
    }


# ── comparison ─────────────────────────────────────────────────────────────────
ANY_OF = ("fix_from", "answer_from")   # expected KB id (or list of ids) must be among the actual ones


def mismatches(expected: dict, actual: dict) -> dict[str, str]:
    """{checked key: what differs}; empty dict = every checked field matches."""
    out = {}
    for key, want in expected.items():
        if key.endswith(("_contains", "_excludes")):
            field, mode = key.rsplit("_", 1)
            got = actual[field]
            items = want if isinstance(want, list) else [want]
            bad = [w for w in items if (w in got) != (mode == "contains")]
            if bad:
                out[key] = f"{field} should {'contain' if mode == 'contains' else 'not contain'} {bad}; got {got!r}"
        elif key in ANY_OF:
            got = actual[key]
            ok = not got if want is None else bool(set(want if isinstance(want, list) else [want]) & set(got or []))
            if not ok:
                out[key] = f"{key}: expected {want!r}, got {got!r}"
        elif actual.get(key) != want:
            out[key] = f"{key}: expected {want!r}, got {actual.get(key)!r}"
    return out


def judge(case: dict, actual: dict) -> dict:
    """fails = unexpected mismatches · known = documented misses seen · fixed = documented misses that now match."""
    diff, known = mismatches(case["expected"], actual), case.get("known_misses", {})
    return {"fails": [m for k, m in diff.items() if k not in known],
            "known": [m for k, m in diff.items() if k in known],
            "fixed": [k for k in known if k not in diff]}


# ── run ────────────────────────────────────────────────────────────────────────
def run_once(cases: dict, only: set[str]) -> list[dict]:
    out = []
    for c in cases["tickets"]:
        if only and c["id"] not in only:
            continue
        actual = ticket_view(analyze_ticket(c["input"], role="support", analyst="eval-cases"))
        out.append({"id": c["id"], "kind": "ticket", "actual": actual, **judge(c, actual)})
        _progress(c, out[-1], actual["outcome"])
    for c in cases["kb_questions"]:
        if only and c["id"] not in only:
            continue
        actual = kb_view(ask_kb(c["question"], role="employee"))
        out.append({"id": c["id"], "kind": "kb", "actual": actual, **judge(c, actual)})
        _progress(c, out[-1], "answered" if actual["answered"] else "not answered")
    return out


def _progress(case: dict, res: dict, shown: str) -> None:
    mark = "FAIL" if res["fails"] else "PASS*" if res["known"] else "PASS"
    print(f"  {mark:5s} {case['id']:4s} {shown:13s} {case['title'][:60]}")
    for f in res["fails"]:
        print(f"          - {f}")
    for f in res["known"]:
        print(f"          * known miss: {f}")
    for k in res["fixed"]:
        print(f"          + known miss on '{k}' now matches: remove it from known_misses")


def write_report(cases: dict, runs: list[list[dict]]) -> tuple[int, int]:
    by_id = {c["id"]: c for c in cases["tickets"] + cases["kb_questions"]}
    ids, n = [r["id"] for r in runs[0]], len(runs)
    results = {i: [next(r for r in run if r["id"] == i) for run in runs] for i in ids}
    passed = [i for i in ids if all(not r["fails"] for r in results[i])]

    def mark(i: str) -> str:
        ok = sum(not r["fails"] for r in results[i])
        sym = "❌" if ok < n else "✅*" if any(r["known"] for r in results[i]) else "✅"
        return f"{sym} {ok}/{n}"

    lines = [
        "# ResolveIQ — Evaluation questions vs expected answers", "",
        f"Run on {datetime.now():%Y-%m-%d %H:%M} through the real pipeline (same functions and roles the app uses). "
        f"Cases and expected answers: [`data/eval_cases.json`](../data/eval_cases.json). "
        f"Regenerate: `python -m build.run_eval_cases --runs {n}`.", "",
        f"**{len(passed)} / {len(ids)} cases match their expected answer"
        + (f" in all {n} runs**" if n > 1 else "**")
        + ". A case passes only if every checked field matches; ✅* = passes, with one documented known miss "
          "(listed at the end, never hidden).", "",
        "How the expected answers were decided: held-out tickets use the dataset's true labels "
        "(never trained on, not in the search index) and the decision table in `src/decide.py`; probes use the "
        "rules in `src/rules.py`, worked out by hand; the expected KB article was chosen by reading the titles.", "",
        "## Tickets (New ticket page, role Support)", "",
        "| ID | Case | Expected | Actual | Priority | Fix from | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in ids:
        if results[i][0]["kind"] != "ticket":
            continue
        a, e = results[i][0]["actual"], by_id[i]["expected"]
        lines.append(f"| {i} | {by_id[i]['title']} | {e.get('outcome', '')} | {a['outcome']} | {a['priority']} | "
                     f"{', '.join(a['fix_from'] or ['–'])} | {mark(i)} |")
    lines += ["", "## Questions (KB Assistant, role Employee)", "",
              "| ID | Question | Expected | Actual | Top source | Steps cite | Result |", "|---|---|---|---|---|---|---|"]
    yes = {True: "answered", False: "not answered"}
    for i in ids:
        if results[i][0]["kind"] != "kb":
            continue
        a, e = results[i][0]["actual"], by_id[i]["expected"]
        lines.append(f"| {i} | {by_id[i]['question']} | {yes[e['answered']]} | {yes[a['answered']]} | "
                     f"{a['top_source'] or '–'} | {', '.join(a['answer_from'] or ['–'])} | {mark(i)} |")

    failing = [i for i in ids if i not in passed]
    if failing:
        lines += ["", "## Mismatches", ""]
        lines += [f"- **{i}** run {k}: {f}" for i in failing for k, r in enumerate(results[i], 1) for f in r["fails"]]
    known = [i for i in ids if by_id[i].get("known_misses")]
    if known:
        lines += ["", "## Known misses (the expected value is the right answer; the app differs on this field)", ""]
        for i in known:
            for field, why in by_id[i]["known_misses"].items():
                seen = sum(any(m.startswith(f"{field}:") or m.startswith(f"{field} ") for m in r["known"])
                           for r in results[i])
                lines.append(f"- **{i}** `{field}` (differs in {seen}/{n} runs): {why}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(passed), len(ids)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=int, default=1, help="repeat the whole set N times (checks LLM stability)")
    p.add_argument("--only", nargs="*", default=[], help="case IDs to run, e.g. T01 K03")
    args = p.parse_args()

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    runs = []
    for k in range(1, args.runs + 1):
        print(f"Run {k}/{args.runs}")
        runs.append(run_once(cases, set(args.only)))
    OUT_JSON.write_text(json.dumps({"created_at": datetime.now().isoformat(timespec="seconds"), "runs": runs},
                                   indent=1, ensure_ascii=False), encoding="utf-8")
    passed, total = write_report(cases, runs)
    print(f"\n{passed}/{total} cases match their expected answer"
          + (f" in all {args.runs} runs" if args.runs > 1 else "")
          + f"\nsaved {OUT_MD.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
