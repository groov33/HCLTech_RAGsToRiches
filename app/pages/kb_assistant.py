"""📚 KB Assistant (Employee): ask a question, get self-help steps from public articles, with sources."""
import streamlit as st

from app import backend, state, ui

state.require_role("employee")
ui.page_header("📚", "KB Assistant",
               "Ask about an IT problem. Answers come only from public knowledge-base articles and their "
               "self-help steps.")

# Test cases, in the order of Docs/DEMO_SCRIPT.md. question -> expected result (shown on hover).
EXAMPLES = {
    "I forgot my password": "Expect 3 self-help steps citing KB-001.",
    # The answer exists in KB-022, but it's internal: the employee must be told to raise a ticket
    "Nobody in the office can connect to the VPN": "Expect 'not in the knowledge base, raise a ticket'. The real "
                                                   "answer (KB-022) is internal, so employees never see it.",
    "VPN connects but shared drives won't open": "Expect self-help steps citing KB-020.",
    "How do I share my calendar?": "Expect 4 self-help steps citing KB-016.",
}
NO_MATCH = "I couldn't find this in the knowledge base. Please raise a ticket with the Service Desk."
LLM_NAME = {"groq": "Groq (cloud model)", "gemini": "Gemini (cloud model)", "ollama": "Ollama (local model)"}

# Confidence = how closely the best article matches the question in meaning (0-1, the retriever's best_score).
# Measured on the eval questions: right article 64-84%; related-but-wrong article 42-49%
# ("laptop screen is cracked" -> "External monitor says no signal"); off-topic 21-34%.
HIGH_MATCH, LOW_MATCH = 0.60, 0.50
CONFIDENCE = {  # level -> (badge colour, icon)
    "High": ("green", "✅"),
    "Medium": ("orange", "⚠️"),
    "Low": ("red", "🔻"),
}
CONFIDENCE_HELP = (f"How closely the best knowledge-base article matches your question. "
                   f"High ≥ {HIGH_MATCH:.0%}, Medium {LOW_MATCH:.0%}–{HIGH_MATCH:.0%}, Low < {LOW_MATCH:.0%}.")

chat: list = st.session_state.setdefault("chat", [])


def confidence_level(score: float) -> str:
    return "High" if score >= HIGH_MATCH else "Medium" if score >= LOW_MATCH else "Low"


def match_badge(score: float, label: str = "") -> str:
    """Colour-coded tag, e.g. ':red-badge[🔻 Low confidence · 34%]'. Text always names the level."""
    level = confidence_level(score)
    colour, icon = CONFIDENCE[level]
    text = f"{icon} {level} confidence · {score:.0%}" if not label else f"{label} {score:.0%}"
    return ui.badge(text, colour)


def ticket_summary(question: str) -> str:
    """Ready-to-paste text for a Service Desk ticket (personal data masked)."""
    return ("Issue (from KB Assistant)\n"
            f"Problem: {backend.mask_pii(question.strip())}\n"
            "Already tried: searched the self-help knowledge base, no matching article found.\n"
            "Please help.")


def render_answer(ans: dict, idx: int) -> None:
    """One assistant answer: numbered steps + citation badges + source quote, then Sources."""
    if not ans.get("answered"):
        if ans.get("no_llm"):
            st.warning("No language model is available right now, so I couldn't write an answer. "
                       "Please raise a ticket with the Service Desk (an administrator can fix this on Settings).")
        else:
            st.markdown(NO_MATCH)
        st.caption("Copy this summary into your ticket (copy button on the right of the box):")
        st.code(ticket_summary(ans.get("question", "")), language=None)
        return

    sources = ans.get("sources") or []
    score = sources[0].get("score", 0.0) if sources else 0.0
    level = confidence_level(score)
    st.markdown(f"Here's what to try:  {match_badge(score)}", help=CONFIDENCE_HELP)
    if level == "Low":
        st.warning("**Low confidence:** no knowledge-base article closely matches your question, so these steps "
                   "may not apply. If they don't help, raise a ticket with the Service Desk.", icon="🔻")
    elif level == "Medium":
        st.caption("⚠️ Medium confidence: the best article is only a partial match. Check each step fits your problem.")

    for i, step in enumerate(ans.get("steps", []), 1):
        cites = " ".join(ui.badge(c, "gray") for c in step.get("cites", []))
        c1, c2 = st.columns([10, 1.4], vertical_alignment="top")
        c1.markdown(f"**{i}.** {step['text']}  {cites}")
        with c2.popover("Source", key=f"kb_src_{idx}_{i}"):
            st.caption("Quoted from: " + ", ".join(step.get("cites", [])))
            st.markdown(f"> {step.get('source_quote') or 'No quote available.'}")

    if ans.get("llm"):
        st.caption(f"Written by {LLM_NAME.get(ans['llm'], ans['llm'])} from the articles below. "
                   "Every step is checked against its source.")

    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            for s in sources:
                why = " · ".join(s.get("why_matched") or [])
                st.markdown(f"**{s['title']}** · {s['kb_id']} · {match_badge(s.get('score', 0.0), 'match')}")
                if why:
                    st.caption(f"Why it matched: {why}")


# ── Top bar: test cases ─────────────────────────────────────────────────────
picked = None
st.markdown("**Test cases**")
st.caption("Click one to ask it. Hover over a button to see the expected result.")
cols = st.columns(2)       # 2 per row, so the full question text fits on each button
for i, (text, expect) in enumerate(EXAMPLES.items()):
    if cols[i % 2].button(text, key=f"kb_ex_{text}", help=expect, width="stretch"):
        picked = text

if not chat:
    ui.empty_state("Type your question below, or click one of the test cases above. "
                   "If the knowledge base can't help, you'll get a summary to paste into a ticket.")

# ── History ─────────────────────────────────────────────────────────────────
for n, msg in enumerate(chat):
    with st.chat_message(msg["role"]):
        if "answer" in msg:
            render_answer(msg["answer"], n)
        elif msg.get("error"):
            st.error(msg["content"])
        else:
            st.markdown(msg["content"])

# ── New question ────────────────────────────────────────────────────────────
question = st.chat_input("Describe your problem, e.g. 'Outlook keeps asking for my password'") or picked
if question:
    chat.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the knowledge base and writing an answer… This can take up to a minute. "
                            "The first question also loads the search models (about 30 s)."):
                answer = backend.ask_kb(question, role="employee")
                if not answer.get("answered") and answer.get("llm") is None and answer.get("sources"):
                    # KBAnswer can't tell "no match" from "no LLM"; check so we don't blame the knowledge base.
                    try:
                        if backend.llm_status()["active"] is None:
                            answer = {**answer, "no_llm": True}
                    except Exception:  # noqa: BLE001
                        pass
        except backend.BackendError as e:
            ui.show_error(e)
            chat.append({"role": "assistant", "content": str(e), "error": True})
        else:
            chat.append({"role": "assistant", "answer": answer})
            render_answer(answer, len(chat) - 1)
