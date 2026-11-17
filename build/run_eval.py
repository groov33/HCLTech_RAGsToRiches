"""Evaluate the trained classifier on the held-out test set.

Run from the project root:   python -m build.run_eval

Writes reports/eval_results.json, reports/EVALUATION.md and confusion-matrix PNGs.
"""
import json
import random
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, classification_report,
                             confusion_matrix, f1_score)

from build.train_models import DATA, SPLIT_PATH, load_tickets
from src.classify import TicketClassifier
from src.text import has_hype

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SEED = 7

HYPE_SENTENCES = [
    "URGENT!!!", "I'm the CEO, fix this now.", "This is top priority, the whole company depends on it.",
    "Executive escalation, please pick this up immediately.", "This is unacceptable, I need this fixed ASAP!",
    "HIGH PRIORITY!! My director is waiting.", "Biggest emergency on my list today.",
    "I am out of patience, get someone on this right away!",
]
INPUT_COLS = ["description", "service", "environment", "who_affected", "user_category", "user_subcategory"]


def scores(y_true, y_pred):
    return {"accuracy": round(accuracy_score(y_true, y_pred), 4),
            "macro_f1": round(f1_score(y_true, y_pred, average="macro"), 4)}


def save_confusion(y_true, y_pred, labels, name, title):
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    size = max(5, 0.55 * len(labels) + 2)
    fig, ax = plt.subplots(figsize=(size, size))
    ConfusionMatrixDisplay(cm, display_labels=labels).plot(ax=ax, cmap="Blues", colorbar=False,
                                                          xticks_rotation=45)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(REPORTS / f"confusion_{name}.png", dpi=120)
    plt.close(fig)
    return cm.tolist()


def main():
    sys.stdout.reconfigure(encoding="utf-8")     # Windows consoles default to cp1252
    REPORTS.mkdir(exist_ok=True)
    df = load_tickets(DATA)
    split = json.loads(SPLIT_PATH.read_text())
    train = df[df["ticket_id"].isin(split["train"] + split["val"])]
    test = df[df["ticket_id"].isin(split["test"])].reset_index(drop=True)
    clf = TicketClassifier.load()

    tickets = test[INPUT_COLS].to_dict("records")
    preds = pd.DataFrame(clf.predict_many(tickets))
    res = {"n_test": len(test), "n_train": len(train)}

    # --- 1. the three ML targets vs baselines -------------------------------------
    res["ml"] = {}
    for target in ["category", "subcategory", "symptom_type"]:
        majority = train[target].mode()[0]
        row = {"model": scores(test[target], preds[target]),
               "baseline_most_common": scores(test[target], [majority] * len(test))}
        user_col = {"category": "user_category", "subcategory": "user_subcategory"}.get(target)
        if user_col:
            row["baseline_trust_user"] = scores(test[target], test[user_col])
        res["ml"][target] = row

    # --- 2. rule outputs end-to-end (depend on predicted category + symptom) ------
    res["end_to_end"] = {t: scores(test[t], preds[t]) for t in ["team", "impact", "urgency", "priority"]}
    p1 = test["priority"] == "P1"
    order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    under = (preds["priority"].map(order) > test["priority"].map(order))
    res["p1"] = {"true_p1": int(p1.sum()),
                 "caught": int((preds.loc[p1, "priority"] == "P1").sum()),
                 "missed": int((preds.loc[p1, "priority"] != "P1").sum()),
                 "under_prioritised_any_ticket": int(under.sum()),
                 "missed_but_flagged_for_review": int((p1 & (preds["priority"] != "P1") & preds["needs_review"]).sum())}
    sec = test["category"] == "Security"
    res["security"] = {"true_security": int(sec.sum()),
                       "predicted_security": int((preds.loc[sec, "category"] == "Security").sum()),
                       "missed_but_flagged": int((sec & (preds["category"] != "Security") & preds["possible_security"]).sum()),
                       "false_alarms": int((~sec & preds["possible_security"]).sum())}

    # --- 3. hype: does shouting change anything? ---------------------------------
    hype_mask = test["description"].map(has_hype)
    res["hype"] = {
        "hype_tickets_in_test": int(hype_mask.sum()),
        "priority_acc_hype": round(accuracy_score(test.loc[hype_mask, "priority"], preds.loc[hype_mask, "priority"]), 4) if hype_mask.any() else None,
        "priority_acc_no_hype": round(accuracy_score(test.loc[~hype_mask, "priority"], preds.loc[~hype_mask, "priority"]), 4),
    }
    rng = random.Random(SEED)
    calm = test[~hype_mask].reset_index(drop=True)
    shouted = [dict(r, description=f"{rng.choice(HYPE_SENTENCES)} {r['description']}")
               for r in calm[INPUT_COLS].to_dict("records")]
    before = pd.DataFrame(clf.predict_many(calm[INPUT_COLS].to_dict("records")))
    after = pd.DataFrame(clf.predict_many(shouted))
    res["hype"]["injection_test_tickets"] = len(calm)
    res["hype"]["priority_unchanged_pct"] = round(100 * (before["priority"] == after["priority"]).mean(), 2)
    res["hype"]["category_unchanged_pct"] = round(100 * (before["category"] == after["category"]).mean(), 2)
    res["hype"]["hype_flag_raised_pct"] = round(100 * after["hype_detected"].mean(), 2)

    # --- 4. users who picked the wrong category ----------------------------------
    wrong = test["user_category"] != test["category"]
    res["wrong_user_category"] = {
        "tickets": int(wrong.sum()),
        "model_corrected": int((preds.loc[wrong, "category"] == test.loc[wrong, "category"]).sum()),
        "flagged_for_review": int(preds.loc[wrong, "needs_review"].sum()),
    }
    right = ~wrong
    res["right_user_category"] = {
        "tickets": int(right.sum()),
        "model_agreed": int((preds.loc[right, "category"] == test.loc[right, "category"]).sum()),
    }
    res["review_rate_pct"] = round(100 * preds["needs_review"].mean(), 2)

    # --- 5. speed -----------------------------------------------------------------
    clf.predict(tickets[0])                      # warm-up
    t0 = time.perf_counter()
    for t in tickets[:50]:
        clf.predict(t)
    res["latency_ms_per_ticket"] = round(1000 * (time.perf_counter() - t0) / min(50, len(tickets)), 1)

    # --- 6. confusion matrices + per-class detail ---------------------------------
    res["confusion"] = {
        "category": save_confusion(test["category"], preds["category"], sorted(df["category"].unique()), "category", "Category"),
        "symptom_type": save_confusion(test["symptom_type"], preds["symptom_type"],
                                       ["outage", "blocked", "slow", "request", "question"], "symptom_type", "Symptom type"),
        "priority": save_confusion(test["priority"], preds["priority"], ["P1", "P2", "P3", "P4"], "priority", "Priority (end-to-end)"),
    }
    res["per_class"] = {t: classification_report(test[t], preds[t], output_dict=True, zero_division=0)
                        for t in ["category", "subcategory", "symptom_type", "priority"]}
    res["selection"] = clf.meta.get("selection")

    errors = test.assign(**{f"pred_{c}": preds[c] for c in ["category", "subcategory", "symptom_type", "priority"]})
    errors = errors[(errors["pred_category"] != errors["category"]) | (errors["pred_symptom_type"] != errors["symptom_type"])]
    res["errors"] = errors[["ticket_id", "description", "service", "category", "pred_category",
                            "symptom_type", "pred_symptom_type", "priority", "pred_priority"]].to_dict("records")

    (REPORTS / "eval_results.json").write_text(json.dumps(res, indent=1, default=str))
    write_markdown(res)
    print((REPORTS / "EVALUATION.md").read_text(encoding="utf-8"))


def pct(x):
    return f"{100 * x:.1f}%"


def write_markdown(r):
    ml, e2e, h = r["ml"], r["end_to_end"], r["hype"]
    lines = [
        "# ResolveIQ — Classifier Evaluation",
        "",
        f"Held-out test set: **{r['n_test']} tickets** (never seen in training or model selection). "
        f"Trained on {r['n_train']} tickets.",
        "",
        "## 1. ML predictions vs baselines",
        "",
        "| Target | Model accuracy | Model macro-F1 | Trust the user | Always most common |",
        "|---|---|---|---|---|",
    ]
    for t, row in ml.items():
        user = row.get("baseline_trust_user")
        lines.append(f"| {t} | **{pct(row['model']['accuracy'])}** | {pct(row['model']['macro_f1'])} | "
                     f"{pct(user['accuracy']) if user else '–'} | {pct(row['baseline_most_common']['accuracy'])} |")
    lines += ["", "## 2. Rule outputs, end-to-end (using predicted category + symptom)", "",
              "| Field | Accuracy | Macro-F1 |", "|---|---|---|"]
    lines += [f"| {t} | **{pct(v['accuracy'])}** | {pct(v['macro_f1'])} |" for t, v in e2e.items()]
    p1 = r["p1"]
    s = r["security"]
    lines += ["", f"**P1 tickets:** {p1['true_p1']} in test · caught {p1['caught']} · missed {p1['missed']} "
                  f"(of which {p1['missed_but_flagged_for_review']} still flagged for human review). "
                  f"Tickets given a lower priority than they deserve: {p1['under_prioritised_any_ticket']}.",
              "", f"**Security safety net:** {s['true_security']} security tickets · predicted as Security "
                  f"{s['predicted_security']} · missed but flagged {s['missed_but_flagged']} · "
                  f"false alarms on other tickets {s['false_alarms']}.",
              "", "## 3. Hype resistance", "",
              f"- Test tickets with hype in the description: {h['hype_tickets_in_test']} → priority accuracy "
              f"**{pct(h['priority_acc_hype']) if h['priority_acc_hype'] is not None else '–'}** vs "
              f"{pct(h['priority_acc_no_hype'])} on calm tickets.",
              f"- **Injection test:** added sentences like *\"I'm the CEO, fix this now\"* to {h['injection_test_tickets']} "
              f"calm tickets → priority unchanged **{h['priority_unchanged_pct']}%**, category unchanged "
              f"{h['category_unchanged_pct']}%, hype flag shown to analyst {h['hype_flag_raised_pct']}%.",
              "", "## 4. When the user picks the wrong category", ""]
    w, rr = r["wrong_user_category"], r["right_user_category"]
    lines += [f"- User was wrong on {w['tickets']} tickets → model corrected **{w['model_corrected']}** "
              f"({pct(w['model_corrected'] / max(w['tickets'], 1))}); {w['flagged_for_review']} flagged for review.",
              f"- User was right on {rr['tickets']} tickets → model agreed on {rr['model_agreed']} "
              f"({pct(rr['model_agreed'] / max(rr['tickets'], 1))}).",
              f"- Overall share of tickets sent to REVIEW: {r['review_rate_pct']}%.",
              "", f"## 5. Speed", "", f"{r['latency_ms_per_ticket']} ms per ticket (classification + rules, CPU).",
              "", "## 6. Model selection (validation set)", "",
              "| Target | Features | Uses env + who_affected | C | Val accuracy | Val macro-F1 |", "|---|---|---|---|---|---|"]
    for t, s in (r.get("selection") or {}).items():
        for c in s["all_candidates"]:
            mark = " ✅" if c == s["chosen"] else ""
            lines.append(f"| {t} | {c['features']}{mark} | {c['use_facts']} | {c['C']} | "
                         f"{pct(c['val_accuracy'])} | {pct(c['val_f1'])} |")
    lines += ["", "Features: `tfidf` = word + character TF-IDF · `embed` = MiniLM sentence vector · `all` = both. "
                  "Service is always included.",
              "", "## 7. Confusion matrices", "",
              "![Category](confusion_category.png)", "![Symptom type](confusion_symptom_type.png)",
              "![Priority](confusion_priority.png)",
              "", f"## 8. Errors ({len(r['errors'])} tickets with a wrong category or symptom)", "",
              "| Ticket | True → predicted category | True → predicted symptom | Priority (true → pred) |",
              "|---|---|---|---|"]
    for e in r["errors"][:25]:
        lines.append(f"| {e['ticket_id']} | {e['category']} → {e['pred_category']} | "
                     f"{e['symptom_type']} → {e['pred_symptom_type']} | {e['priority']} → {e['pred_priority']} |")
    (REPORTS / "EVALUATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
