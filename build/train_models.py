"""Train the 3 text classifiers: category, subcategory, symptom_type.

Run from the project root:   python -m build.train_models

Steps
 1. load tickets, check every label against the rules (catches bad generated rows)
 2. split 70 / 15 / 15, stratified by subcategory (test set saved, never used here)
 3. for each target, try several feature sets, tune C with 5-fold CV on train,
    pick the best by macro-F1 on validation
 4. refit the winner on train + validation with probability calibration
 5. save everything to data/store/models/classifier.joblib
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

from src import rules
from src.features import build_features
from src.text import clean_description, find_date

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "resolveiq_tickets.jsonl"
STORE = ROOT / "data" / "store"
MODEL_PATH = STORE / "models" / "classifier.joblib"
SPLIT_PATH = STORE / "split.json"
SEED = 42

TARGETS = ["category", "subcategory", "symptom_type"]
# (feature kind, use environment + who_affected). Facts are trusted dropdowns,
# so they are allowed; the user's own category guess is never a model input.
CANDIDATES = [("tfidf", False), ("embed", False), ("all", False), ("all", True)]


def load_tickets(path: Path = DATA) -> pd.DataFrame:
    df = pd.read_json(path, lines=True)
    df["text"] = df["description"].map(clean_description)
    return df


def check_rules(df: pd.DataFrame) -> list[str]:
    """Return ids of rows whose labels disagree with the documented rules."""
    bad = []
    for r in df.itertuples():
        when = find_date(r.description)
        i = rules.impact(r.who_affected, r.service, r.category, r.symptom_type)
        u = rules.urgency(r.environment, r.service, r.category, r.symptom_type, when)
        if (rules.team(r.category, r.service), i, u, rules.priority(i, u)) != (r.team, r.impact, r.urgency, r.priority):
            bad.append(r.ticket_id)
    return bad


def split(df: pd.DataFrame):
    train, rest = train_test_split(df, test_size=0.30, stratify=df["subcategory"], random_state=SEED)
    val, test = train_test_split(rest, test_size=0.50, stratify=rest["subcategory"], random_state=SEED)
    return train, val, test


def make_pipeline(kind: str, use_facts: bool) -> Pipeline:
    return Pipeline([
        ("features", build_features(kind, use_facts)),
        ("model", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ])


def select(target: str, train: pd.DataFrame, val: pd.DataFrame):
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    results = []
    for kind, use_facts in CANDIDATES:
        search = GridSearchCV(make_pipeline(kind, use_facts), {"model__C": [1, 3, 10, 30]},
                              scoring="f1_macro", cv=cv, n_jobs=1)
        search.fit(train, train[target])
        pred = search.predict(val)
        results.append({
            "features": kind, "use_facts": use_facts, "C": search.best_params_["model__C"],
            "cv_f1": round(search.best_score_, 4),
            "val_accuracy": round(accuracy_score(val[target], pred), 4),
            "val_f1": round(f1_score(val[target], pred, average="macro"), 4),
        })
        r = results[-1]
        print(f"  {target:13s} {kind:5s} facts={str(use_facts):5s} C={r['C']:<4} "
              f"cv_f1={r['cv_f1']:.3f}  val_acc={r['val_accuracy']:.3f}  val_f1={r['val_f1']:.3f}")
    best = max(results, key=lambda r: (r["val_f1"], r["val_accuracy"]))
    return best, results


def main():
    t0 = time.time()
    df = load_tickets()
    bad = check_rules(df)
    print(f"Loaded {len(df)} tickets; rows disagreeing with rules: {len(bad)}")
    if bad:
        df = df[~df["ticket_id"].isin(bad)]
        print(f"  dropped {len(bad)} bad rows")

    train, val, test = split(df)
    print(f"Split: train {len(train)}  val {len(val)}  test {len(test)}")
    STORE.mkdir(parents=True, exist_ok=True)
    SPLIT_PATH.write_text(json.dumps({
        "seed": SEED, "train": train["ticket_id"].tolist(),
        "val": val["ticket_id"].tolist(), "test": test["ticket_id"].tolist(),
        "dropped_rule_mismatch": bad}, indent=1))

    models, selection = {}, {}
    train_val = pd.concat([train, val])
    for target in TARGETS:
        print(f"\nSelecting model for {target}")
        best, results = select(target, train, val)
        print(f"  -> best: features={best['features']} facts={best['use_facts']} C={best['C']}")
        pipe = make_pipeline(best["features"], best["use_facts"])
        pipe.set_params(model__C=best["C"])
        calibrated = CalibratedClassifierCV(pipe, method="sigmoid", cv=5)
        calibrated.fit(train_val, train_val[target])
        models[target] = calibrated
        selection[target] = {"chosen": best, "all_candidates": results}

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "models": models,
        "selection": selection,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_train": len(train_val),
    }, MODEL_PATH)
    print(f"\nSaved {MODEL_PATH.relative_to(ROOT)}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
