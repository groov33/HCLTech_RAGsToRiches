"""🎫 New ticket — the main screen. Form on the left, evidence-backed result on the right."""
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from app import backend, state, ui
from src.taxonomy import CATEGORIES, ENVIRONMENTS, SERVICES, WHO_AFFECTED

state.require_role("support")
ui.page_header("🎫", "New ticket",
               "Describe the problem. ResolveIQ classifies it, finds similar past tickets and KB articles, "
               "and drafts a cited fix — you review and decide.")

HYPE = "URGENT — I'm the CEO, fix this now! "
# Test cases, in the order of Docs/DEMO_SCRIPT.md. name -> (expected result shown on hover, form values).
# Every one was run through the real pipeline; outcomes and priorities were stable across runs.
EXAMPLES = {
    # Same text the Employee can't get an answer for: the fix comes from internal KB-022
    "VPN outage · P1": ("Expect ⬆️ ESCALATE → Network, P1. Fix from internal KB-022, which employees can't see.", dict(
        description="Nobody in the office can connect to the VPN",
        service="VPN", environment="Production", who_affected="Many teams",
        user_category="Network", user_subcategory="VPN problem")),
    # Happy path: KB-020 covers it, P3 -> RECOMMEND with a cited fix. Also the hype-toggle demo.
    "VPN on, shared drive off": ("Expect ✅ RECOMMEND, P3, 7 cited steps from KB-020. Then switch on the hype "
                                 "toggle: same result plus a hype chip.", dict(
        description="My VPN says connected but the shared drive will not open from home.",
        service="VPN", environment="Not applicable", who_affected="Just me",
        user_category="Network", user_subcategory="VPN problem")),
    # Held-out test ticket INC-00347 (never trained on or indexed) + one added hype sentence
    "INC-00347 · wrong guess": ("Expect ⬆️ ESCALATE → Applications, P2, with a hype chip and a "
                                       "'you chose … model says …' chip.", dict(
        description="I'm getting heat from above. Please pick this up immediately. My workng salary application "
                    "closes just after login. I can see the menu for a moment but can't open a run.",
        service="Payroll System", environment="Production", who_affected="Just me",
        user_category="Device & Software", user_subcategory="Install software")),
    "Uncovered problem": ("Expect ⬆️ ESCALATE → Applications, knowledge gap. No fix is invented.", dict(
        description="Customers see the wrong prices on the company website since this morning.",
        service="Company Website", environment="Production", who_affected="Customers",
        user_category="Business System", user_subcategory="Wrong data")),
    "Vague ticket": ("Expect ❓ NEED INFO, with 2 questions to send back to the user.", dict(
        description="system not working", service="Other / Not sure", environment="Not applicable",
        who_affected="Just me", user_category="Device & Software", user_subcategory="Computer problem")),
    # "slow" comes first, but the model reads the whole sentence and sends it to Security
    "Ransomware · security": ("Expect ⬆️ ESCALATE → Security, P1. Fix from KB-051, containment first.", dict(
        description="My laptop got very slow after I opened an invoice attachment, and now a window says my "
                    "files are encrypted and asks for payment.",
        service="Laptop / Desktop", environment="Production", who_affected="Just me",
        user_category="Device & Software", user_subcategory="Computer problem")),
}


def _load_example(name: str) -> None:
    for field, value in EXAMPLES[name][1].items():
        st.session_state[f"nt_{field}"] = value
    st.session_state["nt_hype"] = False
    st.session_state.pop("result", None)


def _toggle_hype() -> None:
    """Calm vs hype demo: add/remove the pressure sentence, keep the facts identical."""
    d = st.session_state.get("nt_description", "")
    st.session_state["nt_description"] = HYPE + d if st.session_state["nt_hype"] else d.replace(HYPE, "")


# ── Left: the form ──────────────────────────────────────────────────────────
left, right = st.columns([2, 3], gap="large")
with left:
    st.markdown("**Test cases**")
    st.caption("Click one to fill in the form, then **Analyse ticket**. Hover over a button to see the expected result.")
    ex_cols = st.columns(2)
    for i, (name, (expect, _)) in enumerate(EXAMPLES.items()):
        ex_cols[i % 2].button(name, key=f"nt_ex_{i}", on_click=_load_example, args=(name,),
                              help=expect, width="stretch")
    st.toggle("Add \"URGENT — I'm the CEO\" (hype test)", key="nt_hype", on_change=_toggle_hype)

    with st.container(border=True):
        st.text_area("Description *", key="nt_description", height=150,
                     placeholder="Describe what's wrong, what you tried, and any error message")
        st.selectbox("Service", list(SERVICES), key="nt_service")
        st.radio("Environment", ENVIRONMENTS, key="nt_environment", horizontal=True)
        st.radio("Who is affected", WHO_AFFECTED, key="nt_who_affected", horizontal=True)
        # Outside any st.form on purpose: the subcategory list must update when the category changes.
        cat = st.selectbox("Your category guess", list(CATEGORIES), key="nt_user_category")
        if st.session_state.get("nt_user_subcategory") not in CATEGORIES[cat]:
            st.session_state["nt_user_subcategory"] = CATEGORIES[cat][0]
        st.selectbox("Your subcategory guess", CATEGORIES[cat], key="nt_user_subcategory")
        use_llm = st.checkbox("Write a cited fix with the LLM", value=True, key="nt_use_llm",
                              help="Off = classification, similar tickets and KB search only (fast).")
        go = st.button("Analyse ticket", type="primary", width="stretch",
                       disabled=not st.session_state.get("nt_description", "").strip())

    if go:
        ticket = {f: st.session_state[f"nt_{f}"] for f in
                  ("description", "service", "environment", "who_affected", "user_category", "user_subcategory")}
        with st.status("Analysing ticket…", expanded=True) as status:
            st.write("Loading models (first run only, ~30 s)…")
            try:
                backend.warmup()
                st.write("Running the pipeline" + (" — the LLM step can take up to a minute…" if use_llm else "…"))
                result = backend.analyze_ticket(ticket, state.role(), state.analyst(), use_llm=use_llm)
            except backend.BackendError as e:
                status.update(label="Analysis failed", state="error")
                ui.show_error(e)
                st.stop()
            for s in result["trace"]:
                mark = {"done": "✓", "skipped": "–", "failed": "✗", "missing": "·"}.get(s["status"], "·")
                st.write(f"{mark} {s['step']} {s['name']} — {s['ms']:.0f} ms · {s['detail']}")
            status.update(label=f"Done: {result['decision']['outcome'].replace('_', ' ')}", state="complete",
                          expanded=False)
        st.session_state["result"] = result     # reruns (feedback clicks) never re-analyse


# ── Right: the result ───────────────────────────────────────────────────────
def _fix_missing_reason(r: dict) -> str:
    step8 = next((s for s in r["trace"] if s["step"] == "8"), {})
    if "resolve" in r["missing_parts"]:
        return "`src/resolve.py` not built"
    if r["cleaned"]["too_vague"]:
        return "the ticket is too vague to fix — see the questions above"
    if r["kb"] and r["kb"]["knowledge_gap"]:
        return "knowledge gap: no approved KB article fits this ticket"
    if step8.get("status") == "failed":
        return f"{step8.get('detail', 'LLM unavailable')} — " + " ".join(r["decision"]["reasons"])
    return "no fix was written"


def _label_card(col, title: str, field: str, r: dict) -> None:
    lab = r["classification"]
    with col.container(border=True):
        st.caption(title)
        st.markdown(f"**{lab[field]}**")
        ui.confidence_bar(lab["confidence"][field])
        with st.expander("Other candidates"):
            for item in lab["top3"][field]:
                st.write(f"{item['label']} — {item['prob']:.0%}")


def _priority_card(col, r: dict) -> None:
    lab = r["classification"]
    with col.container(border=True):
        st.caption("Priority")
        st.markdown(f"### {ui.priority_badge(lab['priority'])}")
        st.write(lab["priority_reason"])
        st.caption(f"Team **{lab['team']}** · Impact {lab['impact']} · Urgency {lab['urgency']}")


def _fix_tab(r: dict) -> None:
    fix, aid = r["fix"], r["analysis_id"]
    if not fix:
        ui.not_available("Recommended fix", _fix_missing_reason(r))
        return
    articles = {a["kb_id"]: a for a in (r["kb"] or {}).get("articles", [])}
    for p in fix["paths"]:
        with st.container(border=True):
            st.markdown(f"#### {p['title']}  {ui.badge(p['kb_id'], 'gray')}")
            st.caption(f"Why it fits: {p['why_it_fits']}")
            for i, s in enumerate(p["steps"], 1):
                c1, c2 = st.columns([5, 2])
                c1.markdown(f"**{i}.** {s['text']}")
                with c2.popover(" · ".join(s["cites"]) or "no citation", width="stretch"):
                    st.caption("Exact source text")
                    st.markdown(f"> {s['source_quote']}")
            art = articles.get(p["kb_id"])
            if art:
                st.markdown(f"**Verify:** {art['verify']}")
                st.markdown(f"**Escalate if:** {art['escalate_when']}")
    kept = sum(len(p["steps"]) for p in fix["paths"])
    written = kept + fix["dropped_steps"]
    st.caption(f"Citation check: {kept} of {written} steps verified"
               + (f" · {fix['dropped_steps']} step(s) removed (could not be matched to their source)"
                  if fix["dropped_steps"] else "")
               + f" · written by {fix.get('llm_model', fix['llm'])}")
    if fix.get("clarifying_questions"):
        st.markdown("**Questions to ask the user:** " + " · ".join(fix["clarifying_questions"]))
    ui.feedback_widget(aid, "fix", "fix", "fix")


def _similar_tab(r: dict) -> None:
    sim = r["similar"]
    if sim is None:
        ui.not_available("Similar past tickets", "`src/retrieve.py` not built")
        return
    if not sim["tickets"]:
        ui.empty_state("No similar past tickets for this service.")
        return
    if sim["vote"]:
        v = sim["vote"]
        st.markdown(f"**Vote:** {v['agree_count']} of {v['of']} similar tickets are **{v['category']}**")
    for t in sim["tickets"]:
        with st.container(border=True):
            dup = " " + ui.badge("Possible duplicate", "red") if t["is_duplicate"] else ""
            st.markdown(f"**{t['ticket_id']}** · {t['score']:.0%} match · {t['category']} › {t['subcategory']} "
                        f"· {ui.priority_badge(t['priority'])}{dup}")
            st.caption(t["excerpt"])
            st.caption("Why matched: " + " · ".join(t["why_matched"]))
            ui.feedback_widget(r["analysis_id"], "similar_ticket", t["ticket_id"], f"sim_{t['ticket_id']}")


def _kb_tab(r: dict) -> None:
    kb = r["kb"]
    if kb is None:
        ui.not_available("KB articles", "`src/retrieve.py` not built")
        return
    if kb["knowledge_gap"]:
        st.warning("Knowledge gap: no article is a good enough match. Logged for the KB team.")
    if kb["conflict"]:
        st.warning("The top two articles are about different problems — check which one fits.")
    for a in kb["articles"]:
        with st.container(border=True):
            color = "green" if a["access_level"] == "public" else "orange"
            st.markdown(f"**{a['title']}** {ui.badge(a['kb_id'], 'gray')} {ui.badge(a['access_level'], color)} "
                        f"· {a['score']:.0%} match")
            st.caption("Why matched: " + " · ".join(a["why_matched"]))
            with st.expander("Full article"):
                for s in a["steps"]:
                    st.markdown(f"- `{s['step_id']}` {s['text']}")
                st.markdown(f"**Verify:** {a['verify']}")
                st.markdown(f"**Escalate if:** {a['escalate_when']}")
            ui.feedback_widget(r["analysis_id"], "kb_article", a["kb_id"], f"kb_{a['kb_id']}")


def _trace_tab(r: dict) -> None:
    df = pd.DataFrame(r["trace"]).rename(columns={"step": "Step", "name": "What ran", "ms": "Time (ms)",
                                                  "detail": "Key output", "status": "Status"})
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption(f"Total {sum(s['ms'] for s in r['trace']):,.0f} ms · contract v{r['contract_version']} · "
               f"LLM tiebreak: {'used' if r['tiebreak'] else 'not used'} · "
               f"Missing parts: {', '.join(r['missing_parts']) or 'none'}")
    st.markdown("**Thresholds used**")
    st.dataframe(pd.DataFrame(backend.thresholds().items(), columns=["Threshold", "Value"]),
                 hide_index=True, width="stretch")
    if r["fix"] and r["fix"].get("dropped_reasons"):
        with st.expander("Steps removed by the citation check"):
            for x in r["fix"]["dropped_reasons"]:
                st.write(f"- {x}")
    problems = backend.check_result(r)
    with st.expander(f"Contract warnings ({len(problems)})"):
        st.write(problems or "None — the result matches src/contracts.py.")


def _audit_tab(r: dict) -> None:
    st.caption("The full audit record (personal data already masked). Saved to data/store/resolveiq.db.")
    st.download_button("Download JSON", json.dumps(r, indent=1), file_name=f"{r['analysis_id']}.json",
                       mime="application/json")
    st.json(r, expanded=False)


r = st.session_state.get("result")
with right:
    if not r:
        ui.empty_state("Fill in the form (or pick a test case) and click **Analyse ticket**. "
                       "The result, its evidence and a step-by-step trace appear here.")
        st.stop()

    ui.outcome_banner(r["decision"])
    lab = r["classification"]
    chip_list = []
    if lab["hype_detected"]:
        chip_list.append(("Hype detected — ignored for priority", "violet"))
    if lab["user_agrees"] is False:
        chip_list.append((f"You chose {lab['user_category']} — model says {lab['category']}", "orange"))
    if r["tiebreak"] and r["tiebreak"]["used"]:
        chip_list.append((f"LLM tiebreak used: {r['tiebreak']['chosen']}", "blue"))
    if lab["possible_security"]:
        chip_list.append(("🔴 Possible security issue — check with Security team", "red"))
    if r["kb"] and r["kb"]["knowledge_gap"]:
        chip_list.append(("Knowledge gap", "gray"))
    if r["similar"] and any(t["is_duplicate"] for t in r["similar"]["tickets"]):
        chip_list.append(("Possible duplicate of a past ticket", "red"))
    ui.chips(chip_list)

    c = st.columns(4)
    _label_card(c[0], "Category", "category", r)
    _label_card(c[1], "Subcategory", "subcategory", r)
    _label_card(c[2], "Symptom type", "symptom_type", r)
    _priority_card(c[3], r)
    st.caption(f"Combined category score **{lab['confidence']['category_score']:.0%}** "
               f"(0.6 × model + 0.2 × similar tickets agree + 0.2 × your guess agrees; accepted at 75%)"
               + ("  ·  Review: " + "; ".join(lab["review_reasons"]) if lab["review_reasons"] else ""))
    with st.expander("Rate the classification"):
        for f in ("category", "subcategory", "symptom_type", "priority"):
            st.caption(f.replace("_", " ").capitalize() + f": {lab[f]}")
            ui.feedback_widget(r["analysis_id"], "classification", f, f"cls_{f}")

    tabs = st.tabs(["Recommended fix", "Similar past tickets", "KB articles", "Trace", "Audit record"])
    with tabs[0]:
        _fix_tab(r)
    with tabs[1]:
        _similar_tab(r)
    with tabs[2]:
        _kb_tab(r)
    with tabs[3]:
        _trace_tab(r)
    with tabs[4]:
        _audit_tab(r)

    st.divider()
    ts = r["timestamps"]
    if ts["resolved_at"]:
        mins = (datetime.fromisoformat(ts["resolved_at"]) - datetime.fromisoformat(ts["created_at"])).total_seconds() / 60
        st.success(f"Resolved at {ts['resolved_at'][11:16]} · time to resolve {mins:.0f} min")
    elif st.button("Mark resolved", help="Records the resolution time for MTTR. Does not change any real system."):
        when = backend.mark_resolved(r["analysis_id"])
        if when:
            r["timestamps"]["resolved_at"] = when
            st.rerun()
        else:
            st.error("This analysis wasn't saved, so it can't be marked resolved.")
