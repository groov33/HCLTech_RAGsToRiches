"""Predict everything for one ticket.

    from src.classify import TicketClassifier
    clf = TicketClassifier.load()
    result = clf.predict({"description": "...", "service": "VPN", "environment": "Production",
                          "who_affected": "Just me", "user_category": "Network",
                          "user_subcategory": "VPN problem"})

ML predicts category, subcategory and symptom_type. Rules then derive team,
impact, urgency and priority from trusted facts + those predictions.
"""
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import rules
from .taxonomy import CATEGORIES
from .text import clean_description, find_date, has_hype, has_security_cue

MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "store" / "models" / "classifier.joblib"
ACCEPT_THRESHOLD = 0.75     # category score below this -> REVIEW (a human decides; no LLM tiebreak, by choice)
SECURITY_ALERT_PROB = 0.20  # missing a security incident is costly: flag even when not the top guess
SYMPTOM_DOUBT_PROB = 0.25   # runner-up symptom this likely AND it would raise priority -> REVIEW


def _top(classes, probs, k=3):
    order = np.argsort(probs)[::-1][:k]
    return [{"label": str(classes[i]), "prob": round(float(probs[i]), 3)} for i in order]


class TicketClassifier:
    def __init__(self, bundle: dict):
        self.models = bundle["models"]
        self.meta = {k: v for k, v in bundle.items() if k != "models"}

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "TicketClassifier":
        return cls(joblib.load(path))

    @staticmethod
    def _frame(tickets: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(tickets)
        df["text"] = df["description"].map(clean_description)
        return df

    def predict_many(self, tickets: list[dict], today: date | None = None, similar_vote: list | None = None) -> list[dict]:
        df = self._frame(tickets)
        probs = {t: m.predict_proba(df) for t, m in self.models.items()}
        classes = {t: m.classes_ for t, m in self.models.items()}
        out = []
        for i, t in enumerate(tickets):
            vote = similar_vote[i] if similar_vote else None
            out.append(self._one(t, {k: v[i] for k, v in probs.items()}, classes, today, vote))
        return out

    def predict(self, ticket: dict, today: date | None = None, similar_vote: str | None = None) -> dict:
        return self.predict_many([ticket], today, [similar_vote] if similar_vote else None)[0]

    def _one(self, t: dict, p: dict, classes: dict, today, vote) -> dict:
        # 1. category from the model
        cat_classes, cat_p = classes["category"], p["category"]
        category = str(cat_classes[int(np.argmax(cat_p))])
        model_conf = float(cat_p.max())

        # 2. subcategory restricted to the chosen category (keeps the pair consistent)
        sub_classes, sub_p = classes["subcategory"], p["subcategory"].copy()
        allowed = np.isin(sub_classes, CATEGORIES[category])
        masked = np.where(allowed, sub_p, 0.0)
        masked = masked / masked.sum() if masked.sum() > 0 else sub_p
        subcategory = str(sub_classes[int(np.argmax(masked))])

        # 3. symptom type
        sym_classes, sym_p = classes["symptom_type"], p["symptom_type"]
        symptom = str(sym_classes[int(np.argmax(sym_p))])

        # 4. compare with what the user picked (a hint, never a model input)
        user_cat = t.get("user_category")
        user_agrees = user_cat == category if user_cat else None
        parts = [(0.6, model_conf)]
        if vote is not None:
            parts.append((0.2, 1.0 if vote == category else 0.0))
        if user_agrees is not None:
            parts.append((0.2, 1.0 if user_agrees else 0.0))
        category_score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)

        # 5. rules from trusted facts + predictions
        when = find_date(t["description"]) or today
        busy = rules.in_busy_period(t["service"], when)
        imp = rules.impact(t["who_affected"], t["service"], category, symptom)
        urg = rules.urgency(t["environment"], t["service"], category, symptom, when)
        pri = rules.priority(imp, urg)

        reasons = []
        if user_agrees is False:
            reasons.append(f"user chose '{user_cat}', model says '{category}'")
        elif category_score < ACCEPT_THRESHOLD:
            reasons.append(f"unsure about category (score {category_score:.0%})")

        # Security safety net: asymmetric cost, so a weak signal is enough to ask a human.
        security_prob = float(cat_p[list(cat_classes).index("Security")]) if "Security" in cat_classes else 0.0
        possible_security = category != "Security" and (
            security_prob >= SECURITY_ALERT_PROB or has_security_cue(t["description"]) or user_cat == "Security")
        if possible_security:
            reasons.append("possible security issue: check with Security team")

        # Symptom doubt: under-prioritising is the costly mistake, so flag only when the
        # runner-up symptom is plausible AND would give a higher priority (e.g. slow P4 vs blocked P2).
        order = np.argsort(sym_p)[::-1]
        alt_symptom, alt_prob = str(sym_classes[order[1]]), float(sym_p[order[1]])
        if alt_prob >= SYMPTOM_DOUBT_PROB:
            alt_pri = rules.priority(rules.impact(t["who_affected"], t["service"], category, alt_symptom),
                                     rules.urgency(t["environment"], t["service"], category, alt_symptom, when))
            if alt_pri < pri:                          # "P2" < "P4": a smaller number is more urgent
                reasons.append(f"unsure if symptom is '{symptom}' or '{alt_symptom}' "
                               f"({alt_prob:.0%}): priority would be {alt_pri} instead of {pri}")

        return {
            "category": category,
            "subcategory": subcategory,
            "symptom_type": symptom,
            "team": rules.team(category, t["service"]),
            "impact": imp,
            "urgency": urg,
            "priority": pri,
            "priority_reason": rules.explain_priority(imp, urg, t["who_affected"], t["service"],
                                                      t["environment"], symptom, busy),
            "confidence": {
                "category": round(model_conf, 3),
                "subcategory": round(float(masked.max()), 3),
                "symptom_type": round(float(sym_p.max()), 3),
                "category_score": round(category_score, 3),
            },
            "top3": {
                "category": _top(cat_classes, cat_p),
                "subcategory": _top(sub_classes, masked),
                "symptom_type": _top(sym_classes, sym_p),
            },
            "user_category": user_cat,
            "user_agrees": user_agrees,
            "hype_detected": has_hype(t["description"]),   # shown to analyst; never changes priority
            "possible_security": possible_security,
            "needs_review": bool(reasons),
            "review_reasons": reasons,
        }
