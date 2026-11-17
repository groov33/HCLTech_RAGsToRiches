"""Evaluate search (no LLM needed): keyword vs vector vs hybrid.

Run from the project root, after build.train_models and build.build_index:
    python -m build.run_rag_eval              # search metrics only (fast)
    python -m build.run_rag_eval --llm 10     # + full pipeline on 10 test tickets and 17 probe tickets

Test tickets were never indexed, so they can't find themselves.
"Relevant" = same true subcategory. This is an automatic stand-in for hand
labels and is stated as such in the report.

  Similar tickets  Hit@5  = at least one of the top 5 is relevant
                   P@5    = share of the top 5 that is relevant
                   MRR    = 1 / rank of the first relevant ticket (1.0 = always first)
  KB articles      Hit@1 / Hit@3 = the right subcategory's article is #1 / in the top 3
"""
import argparse
import json
import sys
from pathlib import Path

from build.run_eval import INPUT_COLS
from build.train_models import SPLIT_PATH, load_tickets
from src.pipeline import _classifier, _retriever, analyze_ticket

REPORTS = Path(__file__).resolve().parents[1] / "reports"
MODES = ["keyword", "vector", "hybrid"]

# Hand-written probes for "weak or contradictory evidence" (brief §4, Confidence and fallback).
# Every one should go to a human: ESCALATE, REVIEW or NEED_INFO (a clarification request). RECOMMEND = a miss.
PROBES = [
    # 1. no KB article exists for the problem (the 3 gaps left out of the KB on purpose)
    ("knowledge gap", {"description": "Customers see the wrong prices on the company website product pages.",
                       "service": "Company Website", "who_affected": "Customers"}),
    ("knowledge gap", {"description": "My salary this month is lower than it should be, one allowance is missing.",
                       "service": "Payroll System", "who_affected": "Just me"}),
    ("knowledge gap", {"description": "Every printer on the third floor prints blank pages since this morning.",
                       "service": "Printer", "who_affected": "My team"}),
    # 2. too little detail to act on
    ("too vague", {"description": "System not working, please help.", "service": "Other / Not sure",
                   "who_affected": "Just me"}),
    ("too vague", {"description": "It's broken again.", "service": "Other / Not sure", "who_affected": "Just me"}),
    ("too vague", {"description": "Having some issues since yesterday, can someone take a look?",
                   "service": "Other / Not sure", "who_affected": "My team"}),
    # 3. not an IT problem at all
    ("off-topic", {"description": "The coffee machine in the second floor kitchen is leaking water onto the floor.",
                   "service": "Other / Not sure", "who_affected": "My team"}),
    ("off-topic", {"description": "Can I book the large meeting room for our team lunch on Friday?",
                   "service": "Other / Not sure", "who_affected": "My team"}),
    ("off-topic", {"description": "The air conditioning in our open-plan office has been far too cold all week.",
                   "service": "Other / Not sure", "who_affected": "Many teams"}),
    # 4. contradictory evidence: the text says one thing, the chosen service another
    ("contradictory fields", {"description": "The office Wi-Fi keeps dropping my laptop every few minutes and I "
                                             "have to reconnect each time.",
                              "service": "Payroll System", "who_affected": "Just me"}),
    ("contradictory fields", {"description": "The printer next to my desk jams on every page and shows a paper "
                                             "feed error.",
                              "service": "Email", "who_affected": "Just me"}),
    # 5. two different problems in one ticket: one confident fix would ignore the other
    ("two problems", {"description": "The VPN drops every few minutes and separately my email stopped syncing "
                                     "on my phone since this morning.",
                      "service": "VPN", "who_affected": "Just me"}),
    ("two problems", {"description": "My laptop will not charge any more and the printer on my floor prints "
                                     "blank pages.",
                      "service": "Laptop / Desktop", "who_affected": "Just me"}),
    # 6. a security incident hidden behind an ordinary-sounding symptom
    ("hidden security", {"description": "My laptop got very slow after I opened an invoice attachment, and now "
                                        "a window says my files are encrypted and asks for payment.",
                         "service": "Laptop / Desktop", "who_affected": "Just me"}),
    ("hidden security", {"description": "I entered my password on a page linked from an email about my "
                                        "mailbox being full, and now I can't sign in to email.",
                         "service": "Email", "who_affected": "Just me"}),
    # 7. the user's own category contradicts the text
    ("wrong user category", {"description": "I can't print the payroll report: the printer says it is offline "
                                            "although it is switched on.",
                             "service": "Printer", "who_affected": "Just me",
                             "user_category": "Business System", "user_subcategory": "Error or won't open"}),
    ("wrong user category", {"description": "My work account got locked after too many password attempts this "
                                            "morning.",
                             "service": "Company Login", "who_affected": "Just me",
                             "user_category": "Security", "user_subcategory": "Suspicious email"}),
]


def pct(x):
    return f"{100 * x:.1f}%"


def search_metrics(test, preds):
    r = _retriever()
    out = {"tickets": {}, "kb": {}, "kb_with_hint": {}}
    for mode in MODES:
        hit5 = p5 = mrr = kb1 = kb3 = kh1 = kh3 = 0
        for row, pred in zip(test.itertuples(), preds):
            subs = [h["subcategory"] for h in r.search_tickets(row.text, row.service, mode=mode)["tickets"]]
            rel = [s == row.subcategory for s in subs]
            hit5 += any(rel)
            p5 += sum(rel) / 5
            mrr += 1 / (rel.index(True) + 1) if any(rel) else 0
            kb = [h["subcategory"] for h in r.search_kb(row.text, "support", row.service, mode=mode)["articles"]]
            kb1 += bool(kb) and kb[0] == row.subcategory
            kb3 += row.subcategory in kb
            kb = [h["subcategory"] for h in r.search_kb(row.text, "support", row.service, pred["subcategory"],
                                                        pred["confidence"]["subcategory"], mode=mode)["articles"]]
            kh1 += bool(kb) and kb[0] == row.subcategory
            kh3 += row.subcategory in kb
        n = len(test)
        out["tickets"][mode] = {"hit@5": hit5 / n, "p@5": p5 / n, "mrr": mrr / n}
        out["kb"][mode] = {"hit@1": kb1 / n, "hit@3": kb3 / n}
        out["kb_with_hint"][mode] = {"hit@1": kh1 / n, "hit@3": kh3 / n}
        print(f"  {mode:8s} tickets {out['tickets'][mode]}  kb+hint {out['kb_with_hint'][mode]}")
    return out


def llm_metrics(test, n):
    runs = []
    for row in test.head(n).to_dict("records"):
        res = analyze_ticket({c: row[c] for c in INPUT_COLS})
        f = res["fix"] or {}
        kept = sum(len(p["steps"]) for p in f.get("paths", []))
        runs.append({"ticket_id": row["ticket_id"], "decision": res["decision"]["outcome"],
                     "reason": res["decision"]["reasons"][0],
                     "validity": f.get("citation_validity"), "llm": f.get("llm_model"),
                     "written": kept + f.get("dropped_steps", 0), "kept": kept})
        print(f"  {runs[-1]}")
    probes = []
    for kind, p in PROBES:
        res = analyze_ticket({"environment": "Production", "user_category": None, "user_subcategory": None} | p)
        d = res["decision"]
        probes.append({"kind": kind, "description": p["description"], "service": p["service"],
                       "decision": d["outcome"], "to_human": d["outcome"] != "RECOMMEND",
                       "reason": "; ".join(d["reasons"])})
        print(f"  probe {probes[-1]}")
    return {"runs": runs, "probes": probes}


def write_report(m, llm):
    L = ["# ResolveIQ — Search (RAG) Evaluation", "",
         f"Held-out test set: **{m['n_test']} tickets**, never in the search index. "
         "A result counts as relevant when it has the ticket's true subcategory (an automatic stand-in for "
         "hand labels).", "",
         "## 1. Similar past tickets", "", "| Search | Hit@5 | Precision@5 | MRR |", "|---|---|---|---|"]
    L += [f"| {k} | {pct(v['hit@5'])} | {pct(v['p@5'])} | {v['mrr']:.3f} |" for k, v in m["tickets"].items()]
    L += ["", "## 2. KB articles", "", "| Search | Hit@1 | Hit@3 | Hit@1 with classifier hint | Hit@3 with hint |",
          "|---|---|---|---|---|"]
    L += [f"| {k} | {pct(v['hit@1'])} | {pct(v['hit@3'])} | **{pct(m['kb_with_hint'][k]['hit@1'])}** | "
          f"**{pct(m['kb_with_hint'][k]['hit@3'])}** |" for k, v in m["kb"].items()]
    L += ["", "*Hint* = the predicted subcategory boosts matching articles by up to 20% (never filters)."]
    if llm:
        v = [r["validity"] for r in llm["runs"] if r["validity"] is not None and r["written"]]
        L += ["", "## 3. Full pipeline (with LLM)", "",
              f"- Tickets run: {len(llm['runs'])} · average citation validity: "
              f"**{pct(sum(v) / len(v)) if v else '–'}** · LLM: {', '.join({str(r['llm']) for r in llm['runs']})}",
              "", "| Ticket | Decision | Steps kept / written | Reason |", "|---|---|---|---|"]
        L += [f"| {r['ticket_id']} | {r['decision']} | {r['kept']} / {r['written']} | {r.get('reason', '')} |"
              for r in llm["runs"]]
        P = llm["probes"]
        kinds = list(dict.fromkeys(p["kind"] for p in P))
        L += ["", "## 4. Weak or contradictory evidence (probe tickets)", "",
              f"{len(P)} hand-written tickets that should **not** get a confident answer. Pass = the outcome is "
              "ESCALATE, REVIEW or NEED_INFO (a clarification request), i.e. a human sees it before anything "
              "happens. RECOMMEND = a miss.", "",
              f"**Sent to a human: {sum(p['to_human'] for p in P)} / {len(P)} "
              f"({pct(sum(p['to_human'] for p in P) / len(P))})**", "",
              "| Kind | Passed |", "|---|---|"]
        L += [f"| {k} | {sum(p['to_human'] for p in P if p['kind'] == k)} / {sum(p['kind'] == k for p in P)} |"
              for k in kinds]
        L += ["", "| Kind | Ticket | Service | Decision | Human? | Reasons |", "|---|---|---|---|---|---|"]
        L += [f"| {p['kind']} | {p['description']} | {p['service']} | {p['decision']} | "
              f"{'✅' if p['to_human'] else '❌'} | {p['reason']} |" for p in P]
    fa = m["two_problem_false_alarms"]
    L += ["", "## 5. Cost of the two-problem check", "",
          "Each clause of the ticket is searched in the KB on its own; two clauses matching different "
          "subcategories' articles at ≥ 50% similarity send the ticket to REVIEW. On the held-out one-problem "
          f"tickets it fires on **{fa} / {m['n_test']} ({pct(fa / m['n_test'])})**: each of those costs one "
          "human check, whereas a missed second problem gets a confident fix that ignores it. "
          "The 6 two-problem tickets used to pick the 50% threshold were written by us (small sample)."]
    (REPORTS / "RAG_EVALUATION.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", type=int, default=0, help="also run the full pipeline on N test tickets + probes")
    args = ap.parse_args()

    df = load_tickets()
    test = df[df["ticket_id"].isin(json.loads(SPLIT_PATH.read_text())["test"])].reset_index(drop=True)
    preds = _classifier().predict_many(test[INPUT_COLS].to_dict("records"))
    print(f"Search evaluation on {len(test)} test tickets")
    m = search_metrics(test, preds) | {"n_test": len(test)}
    m["two_problem_false_alarms"] = sum(len(_retriever().distinct_problems(t)) > 1 for t in test["text"])
    print(f"  two-problem check fired on {m['two_problem_false_alarms']} / {len(test)} one-problem tickets")
    llm = llm_metrics(test, args.llm) if args.llm else None
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "rag_eval_results.json").write_text(json.dumps(m | {"llm": llm}, indent=1))
    write_report(m, llm)
    print(f"Wrote {REPORTS / 'RAG_EVALUATION.md'}")


if __name__ == "__main__":
    main()
