"""📊 Evaluation (Admin): how good is the classifier, the rules and the search?

Every number on this page is read from reports/eval_results.json and reports/rag_eval_results.json
(via backend.get_eval()). A missing key shows a "Not measured yet" card, never a made-up value.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from app import backend, state, ui

state.require_role("admin")
ui.page_header("📊", "Evaluation",
               "How well ResolveIQ labels, prioritises and searches, measured on tickets it never saw in training.")

RUN_EVAL_CMD = "python -m build.run_eval"
RUN_RAG_CMD = "python -m build.run_rag_eval"
AVG_ROWS = ("accuracy", "macro avg", "weighted avg")


# ── small display helpers (formatting only, no business logic) ──────────────
def _get(d, *keys):
    """Safe nested .get(): _get(data, "ml", "category", "model", "accuracy") -> value or None."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _pct(x, digits: int = 1) -> str:
    """Fraction (0.961) -> '96.1%'."""
    return f"{x * 100:.{digits}f}%" if _num(x) else "—"


def _pct_value(x, digits: int = 1) -> str:
    """Already a percentage (29.44) -> '29.4%'."""
    return f"{x:.{digits}f}%" if _num(x) else "—"


def _int(x) -> str:
    return f"{int(x)}" if _num(x) else "—"


def _not_measured(title: str, reason: str, command: str | None = None) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"Not measured yet — {reason}")
        if command:
            st.code(command, language="bash")


def _kpi(col, label: str, value: str, help: str | None = None, delta: str | None = None,
         note: str | None = None) -> None:
    """Same bordered tile as ui.kpi, plus an optional comparison delta and a caption."""
    if delta is None and note is None:
        ui.kpi(col, label, value, help)
        return
    with col.container(border=True):
        st.metric(label, value, delta=delta, help=help)
        if note:
            st.caption(note)


def _pts_delta(model, other, name: str) -> str | None:
    if not (_num(model) and _num(other)):
        return None
    return f"{(model - other) * 100:+.1f} pts vs {name}"


# ── load ────────────────────────────────────────────────────────────────────
try:
    data = backend.get_eval()
except Exception as e:  # noqa: BLE001 - friendly message, never a traceback
    print(f"[evaluation] get_eval failed: {type(e).__name__}: {str(e)[:200]}")
    data = None
    st.error("The evaluation results could not be read (the file may be damaged). Re-run the evaluation.")


def _rerun_button() -> None:
    """Runs build.run_eval in a subprocess, then reloads the page."""
    st.warning("Re-running trains nothing new but re-scores the whole test set — it takes a while "
               "(about a minute or more). Keep this tab open.", icon="⏳")
    if st.button("🔁 Re-run evaluation", key="au_eval_rerun"):
        with st.spinner(f"Running `{RUN_EVAL_CMD}` …"):
            try:
                proc = subprocess.run([sys.executable, "-m", "build.run_eval"], cwd=str(backend.ROOT),
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=1800)
                ok, tail = proc.returncode == 0, (proc.stderr or proc.stdout or "")[-2000:]
            except subprocess.TimeoutExpired:
                ok, tail = False, "Timed out after 30 minutes."
            except OSError as e:
                ok, tail = False, f"Could not start the evaluation: {type(e).__name__}"
        st.session_state["au_eval_msg"] = ("ok", "") if ok else ("error", tail)
        st.rerun()
    msg = st.session_state.get("au_eval_msg")
    if msg:
        if msg[0] == "ok":
            st.success("Evaluation finished — the numbers below are fresh.")
        else:
            st.error("The evaluation failed. Last lines of its output:")
            st.code(msg[1] or "(no output)", language=None)


if not data:
    ui.empty_state("No evaluation results yet. Run the evaluation once from the project root:")
    st.code(RUN_EVAL_CMD, language="bash")
    with st.expander("Run it from here"):
        _rerun_button()
    st.stop()

# ── header ──────────────────────────────────────────────────────────────────
n_test, n_train = data.get("n_test"), data.get("n_train")
head_l, head_r = st.columns([3, 1], vertical_alignment="center")
with head_l:
    st.markdown(f"**Held-out test set: {_int(n_test)} tickets, trained on {_int(n_train)}. Labels are generated.** "
                + ui.badge("Generated labels", "gray"))
    try:
        when = datetime.fromtimestamp(backend.EVAL_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        st.caption(f"Last evaluation run: {when}")
    except (OSError, AttributeError):
        pass
with head_r:
    with st.popover("🔁 Re-run evaluation", width="stretch"):
        _rerun_button()
msg = st.session_state.get("au_eval_msg")
if msg and msg[0] == "error":
    st.error("The last evaluation re-run failed — open **Re-run evaluation** to see why.")

# ── 1. KPI tiles ────────────────────────────────────────────────────────────
st.subheader("Labels and priority")
ml, e2e = data.get("ml") or {}, data.get("end_to_end") or {}
if not ml and not e2e:
    _not_measured("Classifier accuracy", "no `ml` / `end_to_end` results in eval_results.json.", RUN_EVAL_CMD)
else:
    cols = st.columns(4)
    for col, target, label in ((cols[0], "category", "Category accuracy"),
                               (cols[1], "subcategory", "Subcategory accuracy")):
        model = _get(ml, target, "model", "accuracy")
        trust = _get(ml, target, "baseline_trust_user", "accuracy")
        common = _get(ml, target, "baseline_most_common", "accuracy")
        _kpi(col, label, _pct(model),
             help="Share of test tickets where the model's label matches the true label. "
                  "'Trust the user' = just keep what the user picked; 'most common' = always guess the most frequent label.",
             delta=_pts_delta(model, trust, "trust the user"),
             note=f"Trust the user: {_pct(trust)} · Most common: {_pct(common)}")
    sym = _get(ml, "symptom_type", "model", "accuracy")
    sym_common = _get(ml, "symptom_type", "baseline_most_common", "accuracy")
    _kpi(cols[2], "Symptom type accuracy", _pct(sym),
         help="Outage / blocked / slow / request / question, predicted from the description.",
         delta=_pts_delta(sym, sym_common, "most common"),
         note=f"Most common: {_pct(sym_common)} · the user doesn't pick this")
    pri = _get(e2e, "priority", "accuracy")
    _kpi(cols[3], "Priority accuracy", _pct(pri),
         help="End-to-end: priority from the predicted category + symptom and the ITIL impact × urgency rules.",
         note=f"Macro-F1: {_pct(_get(e2e, 'priority', 'macro_f1'))}")

p1, wrong, right = data.get("p1") or {}, data.get("wrong_user_category") or {}, data.get("right_user_category") or {}
cols = st.columns(4)
if p1:
    _kpi(cols[0], "P1s caught", f"{_int(p1.get('caught'))} / {_int(p1.get('true_p1'))}",
         help="Critical tickets in the test set that were given P1.",
         note=f"Missed: {_int(p1.get('missed'))} · of those still flagged for review: "
              f"{_int(p1.get('missed_but_flagged_for_review'))}")
else:
    with cols[0]:
        _not_measured("P1s caught", "no `p1` results.")
if wrong:
    _kpi(cols[1], "Wrong user category corrected",
         f"{_int(wrong.get('model_corrected'))} / {_int(wrong.get('tickets'))}",
         help="Tickets where the user picked the wrong category and the model fixed it.",
         note=f"Flagged for review: {_int(wrong.get('flagged_for_review'))}"
              + (f" · user was right on {_int(right.get('tickets'))}, model agreed on {_int(right.get('model_agreed'))}"
                 if right else ""))
else:
    with cols[1]:
        _not_measured("Wrong user category corrected", "no `wrong_user_category` results.")
_kpi(cols[2], "Sent to REVIEW", _pct_value(data.get("review_rate_pct")),
     help="Share of test tickets the system hands to a human to double-check instead of recommending directly.")
lat = data.get("latency_ms_per_ticket")
_kpi(cols[3], "Time per ticket", f"{lat:.0f} ms" if _num(lat) else "—",
     help="Classification + rules on CPU, averaged over the test set (search and LLM not included).")

if e2e:
    with st.expander("Other rule outputs (team, impact, urgency)"):
        rows = [{"Field": k.capitalize(), "Accuracy": _pct(_get(v, "accuracy")), "Macro-F1": _pct(_get(v, "macro_f1"))}
                for k, v in e2e.items() if isinstance(v, dict)]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ── 2. Safety cards ─────────────────────────────────────────────────────────
c_hype, c_sec = st.columns(2)
with c_hype:
    hype = data.get("hype") or {}
    if not hype:
        _not_measured("Hype resistance", "no `hype` results.", RUN_EVAL_CMD)
    else:
        with st.container(border=True):
            st.markdown("**🧯 Hype resistance** — shouting doesn't change the priority")
            a, b = st.columns(2)
            a.metric("Priority accuracy, hype tickets", _pct(hype.get("priority_acc_hype")),
                     help=f"{_int(hype.get('hype_tickets_in_test'))} test tickets with words like 'URGENT!!!'.")
            b.metric("Priority accuracy, calm tickets", _pct(hype.get("priority_acc_no_hype")))
            st.caption(
                f"Injection test: added lines like *\"I'm the CEO, fix this now\"* to "
                f"{_int(hype.get('injection_test_tickets'))} calm tickets → priority unchanged "
                f"**{_pct_value(hype.get('priority_unchanged_pct'))}**, category unchanged "
                f"**{_pct_value(hype.get('category_unchanged_pct'))}**, hype flag shown to the analyst "
                f"**{_pct_value(hype.get('hype_flag_raised_pct'))}**.")
with c_sec:
    sec = data.get("security") or {}
    if not sec:
        _not_measured("Security safety net", "no `security` results.", RUN_EVAL_CMD)
    else:
        with st.container(border=True):
            st.markdown("**🛡️ Security safety net** — security issues must not slip through")
            a, b, c = st.columns(3)
            a.metric("Caught", f"{_int(sec.get('predicted_security'))} / {_int(sec.get('true_security'))}",
                     help="True security tickets that the model labelled Security.")
            b.metric("Missed but flagged", _int(sec.get("missed_but_flagged")),
                     help="Missed security tickets that still got the 'possible security issue' flag for a human.")
            c.metric("False alarms", _int(sec.get("false_alarms")),
                     help="Other tickets flagged as a possible security issue. Cheap: a human takes a quick look.")

# ── 3. Confusion matrices ───────────────────────────────────────────────────
st.subheader("Where the model gets confused")
st.caption("Rows = true label, columns = predicted label. Everything on the diagonal is correct.")

FIXED_ORDER = {  # same label order build/run_eval.py passes to confusion_matrix()
    "symptom_type": ["outage", "blocked", "slow", "request", "question"],
    "priority": ["P1", "P2", "P3", "P4"],
}


def _labels_for(target: str, matrix: list) -> list[str] | None:
    """Label order for a stored matrix; checked against per_class support so a wrong guess never shows."""
    per = _get(data, "per_class", target) or {}
    classes = sorted(k for k in per if k not in AVG_ROWS)
    labels = FIXED_ORDER.get(target, classes)
    if len(labels) != len(matrix) or not per:
        return None
    for lab, row in zip(labels, matrix):
        support = _get(per, lab, "support")
        if not _num(support) or int(support) != sum(row):
            return None
    return labels


def _heatmap(matrix: list, labels: list[str], title: str) -> alt.LayerChart:
    df = pd.DataFrame([{"True": t, "Predicted": p, "Tickets": matrix[i][j]}
                       for i, t in enumerate(labels) for j, p in enumerate(labels)])
    peak = max(1, int(df["Tickets"].max()))
    base = alt.Chart(df).encode(
        x=alt.X("Predicted:N", sort=labels, title="Predicted", axis=alt.Axis(labelAngle=-35)),
        y=alt.Y("True:N", sort=labels, title="True"),
    )
    rect = base.mark_rect(stroke="rgba(128,128,128,0.35)").encode(
        color=alt.Color("Tickets:Q", scale=alt.Scale(scheme="blues", domain=[0, peak]), legend=None),
        tooltip=["True", "Predicted", "Tickets"],
    )
    text = base.mark_text(fontSize=13, fontWeight="bold").encode(
        text=alt.Text("Tickets:Q"),
        # fixed dark/white text on the cell colour, so it reads in light and dark theme
        color=alt.condition(alt.datum.Tickets > peak * 0.5, alt.value("#FFFFFF"), alt.value("#1F2937")),
    )
    side = max(220, 52 * len(labels))
    return (rect + text).properties(title=title, width=side, height=side)


conf = data.get("confusion") or {}
tabs = st.tabs(["Category", "Symptom type", "Priority"])
for tab, (target, title) in zip(tabs, (("category", "Category"), ("symptom_type", "Symptom type"),
                                       ("priority", "Priority (end-to-end)"))):
    with tab:
        matrix = conf.get(target)
        labels = _labels_for(target, matrix) if isinstance(matrix, list) and matrix else None
        if labels:
            st.altair_chart(_heatmap(matrix, labels, title), width="content")
        else:
            img = backend.ROOT / "reports" / f"confusion_{target}.png"
            if img.exists():
                st.image(str(img), caption=f"{title} (saved image)", width=520)
            else:
                _not_measured(f"{title} confusion matrix", "no matrix in eval_results.json.", RUN_EVAL_CMD)

# ── 4. Per-class table ──────────────────────────────────────────────────────
per_class = data.get("per_class") or {}
if per_class:
    with st.expander("Per-class detail (precision, recall, F1)"):
        st.caption("Precision = when the model says X, how often it's right. Recall = of all real X, how many it found.")
        names = {"category": "Category", "subcategory": "Subcategory", "symptom_type": "Symptom type",
                 "priority": "Priority"}
        keys = [k for k in names if isinstance(per_class.get(k), dict)] + \
               [k for k in per_class if k not in names and isinstance(per_class.get(k), dict)]
        for tab, key in zip(st.tabs([names.get(k, k) for k in keys]), keys):
            with tab:
                rows = []
                for cls, m in per_class[key].items():
                    if not isinstance(m, dict):
                        continue
                    rows.append({"Class": cls,
                                 "Precision": (m.get("precision") or 0) * 100,
                                 "Recall": (m.get("recall") or 0) * 100,
                                 "F1": (m.get("f1-score") or 0) * 100,
                                 "Test tickets": int(m.get("support") or 0)})
                pc = st.column_config.ProgressColumn
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
                    "Precision": pc(format="%.0f%%", min_value=0, max_value=100),
                    "Recall": pc(format="%.0f%%", min_value=0, max_value=100),
                    "F1": pc(format="%.0f%%", min_value=0, max_value=100)})
else:
    _not_measured("Per-class detail", "no `per_class` results.", RUN_EVAL_CMD)

# ── 5. Search quality (rag_eval_results.json) ───────────────────────────────
st.subheader("Search quality: keyword vs vector vs hybrid")
st.caption("Why it matters: meaning-based (vector) search finds tickets that describe the same problem in other "
           "words, so the evidence beats superficial keyword matches.")
rag = data.get("rag")
SECTIONS = {"tickets": "Similar past tickets", "kb": "KB articles",
            "kb_with_hint": "KB articles, with the classifier's hint"}
METRIC_NAMES = {"hit@1": "Hit@1", "hit@3": "Hit@3", "hit@5": "Hit@5", "p@5": "Precision@5", "mrr": "MRR"}
METHODS = ["keyword", "vector", "hybrid"]
METHOD_COLORS = ["#8B95A5", "#2563EB", "#D97706"]   # grey / blue / amber: readable on light and dark

if not isinstance(rag, dict):
    _not_measured("Search quality", "reports/rag_eval_results.json not found.", RUN_RAG_CMD)
else:
    rows = []
    for sec_key, sec_name in SECTIONS.items():
        for method in METHODS:
            for metric, value in (_get(rag, sec_key, method) or {}).items():
                if _num(value):
                    rows.append({"Section": sec_name, "Search": method,
                                 "Metric": METRIC_NAMES.get(metric, metric), "Score": value})
    if not rows:
        _not_measured("Search quality", "no keyword / vector / hybrid scores in rag_eval_results.json.", RUN_RAG_CMD)
    else:
        st.caption(f"{_int(rag.get('n_test'))} held-out test tickets, never in the search index. A result counts as "
                   "relevant when it has the ticket's true subcategory. Hit@k = a relevant result is in the top k · "
                   "Precision@5 = share of the top 5 that are relevant · MRR = how high the first relevant result "
                   "ranks (1.0 = always first).")
        df = pd.DataFrame(rows)
        cols = st.columns(len(df["Section"].unique()))
        for col, sec_name in zip(cols, [s for s in SECTIONS.values() if s in set(df["Section"])]):
            part = df[df["Section"] == sec_name]
            chart = alt.Chart(part).mark_bar(cornerRadiusEnd=2).encode(
                x=alt.X("Metric:N", title=None, sort=list(METRIC_NAMES.values()), axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("Search:N", sort=METHODS),
                y=alt.Y("Score:Q", title=None, scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                color=alt.Color("Search:N", sort=METHODS, legend=alt.Legend(orient="bottom", title=None),
                                scale=alt.Scale(domain=METHODS, range=METHOD_COLORS)),
                tooltip=["Search", "Metric", alt.Tooltip("Score:Q", format=".1%")],
            ).properties(title=sec_name, height=260)
            col.altair_chart(chart, width="stretch")
            best = part.loc[part.groupby("Metric")["Score"].idxmax()]
            col.caption("Best: " + " · ".join(f"{r.Metric} → {r.Search}" for r in best.itertuples()))
        table = df.assign(Column=df["Section"] + " · " + df["Metric"]).pivot(
            index="Search", columns="Column", values="Score").reindex(METHODS).dropna(how="all")
        ordered = [f"{s} · {m}" for s in SECTIONS.values() for m in METRIC_NAMES.values()
                   if f"{s} · {m}" in table.columns]
        st.dataframe(table[ordered].map(lambda v: _pct(v) if _num(v) else "—"), width="stretch")

    # Fix quality + fallback (full pipeline with an LLM)
    llm = rag.get("llm")
    c_fix, c_fb = st.columns(2)
    with c_fix:
        runs = (llm or {}).get("runs") or []
        valid = [r.get("validity") for r in runs
                 if isinstance(r, dict) and _num(r.get("validity")) and r.get("written")]
        if not valid:
            _not_measured("Fix quality (citation validity)",
                          "no fix steps were written by an LLM in the last search evaluation. "
                          f"Run `{RUN_RAG_CMD} --llm 10` with an LLM available.", f"{RUN_RAG_CMD} --llm 10")
        else:
            with st.container(border=True):
                st.markdown("**📎 Fix quality** — every fix step must cite a real source")
                kept = sum(r.get("kept") or 0 for r in runs)
                written = sum(r.get("written") or 0 for r in runs)
                a, b = st.columns(2)
                a.metric("Average citation validity", _pct(sum(valid) / len(valid)),
                         help="Share of fix steps whose citation points to a real KB step or past ticket.")
                b.metric("Steps kept / written", f"{kept} / {written}")
                models = sorted({str(r.get("llm")) for r in runs if r.get("llm")})
                st.caption(f"{len(runs)} tickets run" + (f" · LLM: {', '.join(models)}" if models else ""))
        if runs:
            with st.expander("Tickets run through the full pipeline"):
                st.dataframe(pd.DataFrame([{"Ticket": r.get("ticket_id"), "Decision": r.get("decision"),
                                            "Steps kept": r.get("kept"), "Steps written": r.get("written"),
                                            "Citation validity": _pct(r.get("validity")),
                                            "LLM": r.get("llm") or "none"} for r in runs if isinstance(r, dict)]),
                             hide_index=True, width="stretch")
    with c_fb:
        probes = [p for p in ((llm or {}).get("probes") or []) if isinstance(p, dict)]
        if not probes:
            _not_measured("Fallback to a human",
                          f"no probe tickets were run. Run `{RUN_RAG_CMD} --llm 10` with an LLM available.",
                          f"{RUN_RAG_CMD} --llm 10")
        else:
            to_human = sum(1 for p in probes if p.get("decision") and p.get("decision") != "RECOMMEND")
            with st.container(border=True):
                st.markdown("**🙋 Fallback** — tickets it can't solve go to a human")
                st.metric("Probe tickets sent to a human", f"{to_human} / {len(probes)}",
                          delta=f"{to_human / len(probes):.0%}", delta_color="off",
                          help="Hand-written tickets with no matching article, or too vague to act on. "
                               "Each should end as REVIEW, ESCALATE or NEED INFO — never RECOMMEND.")
                with st.expander("Probe tickets"):
                    st.dataframe(pd.DataFrame([{"Kind": p.get("kind"),
                                                "Ticket": backend.mask_pii(str(p.get("description") or "")),
                                                "Decision": p.get("decision"), "Reason": p.get("reason")}
                                               for p in probes]),
                                 hide_index=True, width="stretch")

# ── 6. Example mistakes ─────────────────────────────────────────────────────
errors = [e for e in (data.get("errors") or []) if isinstance(e, dict)]
if errors:
    with st.expander(f"Example mistakes ({len(errors)} test tickets with a wrong category or symptom type)"):
        rows = []
        for e in errors:
            def _pair(true, pred):
                return f"{true} ✓" if true == pred else f"{true} → {pred}"
            rows.append({"Ticket": e.get("ticket_id"),
                         "Description": backend.mask_pii(str(e.get("description") or "")),
                         "Service": e.get("service"),
                         "Category (true → predicted)": _pair(e.get("category"), e.get("pred_category")),
                         "Symptom (true → predicted)": _pair(e.get("symptom_type"), e.get("pred_symptom_type")),
                         "Priority (true → predicted)": _pair(e.get("priority"), e.get("pred_priority"))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Description": st.column_config.TextColumn(width="large")})

st.divider()
st.caption("Full write-ups with the method and every table: `reports/EVALUATION.md` (classifier, rules, safety) "
           "and `reports/RAG_EVALUATION.md` (search and fix quality). Labels in the dataset are generated, "
           "so treat these numbers as a sanity check, not a production benchmark.")
