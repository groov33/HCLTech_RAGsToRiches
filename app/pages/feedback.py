"""💬 Feedback & audit (Admin): what support staff said about the results, knowledge gaps, and every stored analysis."""
import pandas as pd
import streamlit as st

from app import backend, state, ui

state.require_role("admin")
ui.page_header("💬", "Feedback & audit",
               "How useful the suggestions were, which articles need work, where the knowledge base has gaps, "
               "and the full record of every analysis.")

VERDICT_COLS = ["useful", "incorrect", "unresolved"]
EVERYONE = "Everyone"


def safe(call, default):
    """Run a backend call; on failure show a friendly message (never a traceback) and return default."""
    try:
        return call()
    except backend.BackendError as e:
        ui.show_error(e)
    except Exception as e:  # noqa: BLE001
        print(f"[feedback page] {type(e).__name__}: {str(e)[:200]}")
        st.error("Couldn't read the stored records. Check the console for details.")
    return default


def verdict_table(df: pd.DataFrame, by: str, label: str) -> pd.DataFrame:
    """Useful / incorrect / unresolved counts per value of `by`, plus a total."""
    t = pd.crosstab(df[by], df["verdict"]).reindex(columns=VERDICT_COLS, fill_value=0)
    t["total"] = t.sum(axis=1)
    t.columns = [c.capitalize() for c in t.columns]
    return t.rename_axis(label).reset_index()


# ── Load ────────────────────────────────────────────────────────────────────
all_feedback = safe(lambda: backend.get_feedback(None), [])
all_audit = safe(lambda: backend.get_audit({}), [])

people = sorted(({f.get("analyst", "") for f in all_feedback} | {r.get("analyst", "") for r in all_audit}) - {""})
person = st.selectbox("Support person", [EVERYONE, *people], key="au_person",
                      help="Filters the whole page: feedback, knowledge gaps and audit records.")
analyst = None if person == EVERYONE else person

feedback = all_feedback if analyst is None else [f for f in all_feedback if f["analyst"] == analyst]
audit = all_audit if analyst is None else [r for r in all_audit if r.get("analyst") == analyst]
gaps = [r for r in audit if r.get("kb") and r["kb"].get("knowledge_gap")]

# ── KPIs ────────────────────────────────────────────────────────────────────
fb = pd.DataFrame(feedback, columns=["feedback_id", "analysis_id", "analyst", "target_type", "target_id",
                                     "verdict", "comment", "created_at"])
n = len(fb)
k1, k2, k3, k4 = st.columns(4)
ui.kpi(k1, "Feedback given", str(n), "Every Useful / Incorrect / Unresolved click saved on New ticket.")
ui.kpi(k2, "Useful", ui.pct((fb["verdict"] == "useful").mean() if n else None), "Share of feedback marked Useful.")
ui.kpi(k3, "Incorrect", ui.pct((fb["verdict"] == "incorrect").mean() if n else None),
       "Share of feedback marked Incorrect.")
ui.kpi(k4, "Knowledge gaps", str(len(gaps)), "Analyses where no knowledge-base article matched well enough.")

# ── Feedback tables ─────────────────────────────────────────────────────────
st.subheader("Feedback")
if not n:
    ui.empty_state("No feedback yet — analyse a ticket on New ticket (Support) and rate the result.")
else:
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**Per support person**")
        st.dataframe(verdict_table(fb, "analyst", "Support person"), hide_index=True, width="stretch")
    with c2.container(border=True):
        st.markdown("**Per knowledge-base article** · most *incorrect* first")
        art = fb[fb["target_type"] == "kb_article"]
        if art.empty:
            st.caption("No feedback on articles yet.")
        else:
            t = verdict_table(art, "target_id", "Article").sort_values(["Incorrect", "Total"], ascending=False)
            titles = safe(lambda: {a["kb_id"]: a["title"] for a in backend.list_kb({}, role="admin")}, {})
            t.insert(1, "Title", t["Article"].map(titles).fillna(""))
            st.dataframe(t, hide_index=True, width="stretch")

    with st.expander(f"All feedback ({n})"):
        st.dataframe(fb.sort_values("created_at", ascending=False), hide_index=True, width="stretch",
                     column_config={"feedback_id": None, "analyst": "Support person", "target_type": "About",
                                    "target_id": "Item", "verdict": "Verdict", "comment": "Comment",
                                    "analysis_id": "Analysis", "created_at": "When"})
    csv = fb.assign(comment=fb["comment"].fillna("").map(backend.mask_pii)).to_csv(index=False).encode("utf-8")
    st.download_button("Export feedback CSV", csv, "resolveiq_feedback.csv", "text/csv", key="au_fb_csv",
                       icon="⬇️")

# ── Knowledge gaps ──────────────────────────────────────────────────────────
st.subheader("Knowledge gaps")
st.caption("Tickets where no article matched well enough. Each is a candidate for a new knowledge-base article.")
if not gaps:
    ui.empty_state("No knowledge gaps found. They appear here when an analysed ticket has no good article match.")
else:
    st.dataframe(pd.DataFrame([{
        "Analysis": r["analysis_id"],
        "Description": (r["ticket"].get("description") or "")[:120],
        "Predicted subcategory": r["classification"].get("subcategory"),
        "Created": r["timestamps"].get("created_at"),
    } for r in gaps]), hide_index=True, width="stretch")

# ── Audit records (FR-08) ───────────────────────────────────────────────────
st.divider()
st.subheader("Audit records")
st.caption("Every analysis is stored with its input, predictions, evidence, fix, decision and timestamps. "
           "Personal data is masked. Select a row to see the full record.")

f1, f2 = st.columns(2)
outcomes = f1.multiselect("Outcome", list(ui.OUTCOME), key="au_outcome",
                          format_func=lambda o: ui.OUTCOME[o][1])
priorities = f2.multiselect("Priority", list(ui.PRIORITY_COLOR), key="au_priority")
filters = {"outcome": outcomes, "priority": priorities, "analyst": analyst}
records = [r for r in audit
           if (not outcomes or r["decision"]["outcome"] in outcomes)
           and (not priorities or r["classification"]["priority"] in priorities)]

if not all_audit:
    ui.empty_state("No analyses yet — analyse a ticket on New ticket (Support) and it will be recorded here.")
elif not records:
    ui.empty_state("No analyses match these filters. Clear a filter to see more.")
else:
    table = pd.DataFrame([{
        "Time": r["timestamps"].get("created_at"),
        "Support person": r.get("analyst"),
        "Outcome": ui.OUTCOME.get(r["decision"]["outcome"], ("", r["decision"]["outcome"]))[1],
        "Priority": r["classification"]["priority"],
        "Category": r["classification"]["category"],
        "Confidence": round(100 * r["decision"]["confidence"]),
        "Resolved": "yes" if r["timestamps"].get("resolved_at") else "no",
    } for r in records])
    event = st.dataframe(table, hide_index=True, width="stretch", key="au_table", on_select="rerun",
                         selection_mode="single-row",
                         column_config={"Confidence": st.column_config.NumberColumn(format="%d%%")})

    e1, e2, _ = st.columns([1, 1, 4])
    csv = safe(lambda: backend.export_audit(filters, "csv"), None)
    js = safe(lambda: backend.export_audit(filters, "json"), None)
    if csv is not None:
        e1.download_button("Export CSV", csv, "resolveiq_audit.csv", "text/csv", key="au_csv", icon="⬇️")
    if js is not None:
        e2.download_button("Export JSON", js, "resolveiq_audit.json", "application/json", key="au_json",
                           icon="⬇️")

    rows = [i for i in (event.selection.rows if event is not None else []) if i < len(records)]
    if not rows:
        st.caption("Select a row above to see the full record.")
    else:
        r = records[rows[0]]
        lab, dec, ts, tk = r["classification"], r["decision"], r["timestamps"], r["ticket"]
        with st.container(border=True):
            st.markdown(f"#### {r['analysis_id']}  {ui.outcome_badge(dec['outcome'])} "
                        f"{ui.priority_badge(lab['priority'])}")
            st.caption(f"Analysed by {r.get('analyst')} ({r.get('role')}) · created {ts.get('created_at')} · "
                       f"recommendation ready {ts.get('recommended_at') or '—'} · "
                       f"resolved {ts.get('resolved_at') or 'not yet'}")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Input** (personal data masked)")
                st.markdown(f"> {tk.get('description', '')}")
                st.caption(f"Service: {tk.get('service')} · Environment: {tk.get('environment')} · "
                           f"Who is affected: {tk.get('who_affected')} · "
                           f"User's guess: {tk.get('user_category')} › {tk.get('user_subcategory')}")
            with c2:
                st.markdown("**Predictions**")
                st.markdown(f"{lab['category']} › {lab['subcategory']} · {lab.get('symptom_type', '')}  \n"
                            f"Priority **{lab['priority']}** · team {lab.get('team', '—')}")
                st.caption(lab.get("priority_reason", ""))
                ui.confidence_bar(lab["confidence"]["category_score"], "Category confidence")

            c3, c4 = st.columns(2)
            with c3:
                st.markdown("**Similar past tickets**")
                sim = (r.get("similar") or {}).get("tickets", [])
                if sim:
                    st.dataframe(pd.DataFrame([{"Ticket": t["ticket_id"], "Match": round(100 * t["score"]),
                                                "Subcategory": t.get("subcategory")} for t in sim]),
                                 hide_index=True, width="stretch",
                                 column_config={"Match": st.column_config.NumberColumn(format="%d%%")})
                else:
                    st.caption("None recorded.")
            with c4:
                st.markdown("**Knowledge-base articles**")
                arts = (r.get("kb") or {}).get("articles", [])
                if arts:
                    st.dataframe(pd.DataFrame([{"Article": a["kb_id"], "Title": a.get("title"),
                                                "Match": round(100 * a["score"])} for a in arts]),
                                 hide_index=True, width="stretch",
                                 column_config={"Match": st.column_config.NumberColumn(format="%d%%")})
                else:
                    st.caption("None recorded.")
                if (r.get("kb") or {}).get("knowledge_gap"):
                    st.markdown(ui.badge("knowledge gap", "orange"))

            st.markdown("**Recommended fix**")
            fix = r.get("fix")
            if not fix or not fix.get("paths"):
                st.caption("No fix was written for this analysis.")
            else:
                for p in fix["paths"]:
                    st.markdown(f"*{p.get('kb_id')} · {p.get('title')}* — {p.get('why_it_fits', '')}")
                    for i, s in enumerate(p.get("steps", []), 1):
                        st.markdown(f"{i}. {s['text']}  " + " ".join(ui.badge(c, "gray") for c in s.get("cites", [])))
                st.caption(f"Written by {fix.get('llm_model') or fix.get('llm')} · citation check "
                           f"{fix.get('citation_validity', 0):.0%} passed · {fix.get('dropped_steps', 0)} step(s) dropped")

            st.markdown("**Decision**")
            st.markdown(f"{ui.outcome_badge(dec['outcome'])} · confidence {dec['confidence']:.0%}"
                        + (f" · hand to **{dec['escalate_to']}**" if dec.get("escalate_to") else ""))
            for reason in dec.get("reasons", []):
                st.markdown(f"- {reason}")
            for q in dec.get("questions") or []:
                st.markdown(f"- ❓ {q}")

            st.markdown("**Feedback on this analysis**")
            mine = [f for f in all_feedback if f["analysis_id"] == r["analysis_id"]]
            if mine:
                st.dataframe(pd.DataFrame(mine)[["analyst", "target_type", "target_id", "verdict", "comment",
                                                 "created_at"]],
                             hide_index=True, width="stretch",
                             column_config={"analyst": "Support person", "target_type": "About",
                                            "target_id": "Item", "verdict": "Verdict", "comment": "Comment",
                                            "created_at": "When"})
            else:
                st.caption("No feedback given on this analysis.")

            with st.expander("Full record (JSON)"):
                st.json(r, expanded=False)
