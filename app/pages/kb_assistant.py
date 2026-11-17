"""📚 KB Assistant (Employee): ask a question, get self-help steps from public articles, with sources."""
import streamlit as st

from app import backend, state, ui

state.require_role("employee")
ui.page_header("📚", "KB Assistant",
               "Ask about an IT problem. Answers come only from public knowledge-base articles and their "
               "self-help steps.")

EXAMPLES = ["I forgot my password", "VPN connects but shared drives won't open", "How do I share my calendar?"]
NO_MATCH = "I couldn't find this in the knowledge base. Please raise a ticket with the Service Desk."
LLM_NAME = {"groq": "Groq (cloud model)", "ollama": "Ollama (local model)"}

chat: list = st.session_state.setdefault("chat", [])


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

    st.markdown("Here's what to try:")
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

    sources = ans.get("sources") or []
    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            for s in sources:
                why = " · ".join(s.get("why_matched") or [])
                st.markdown(f"**{s['title']}** · {s['kb_id']} · match {s.get('score', 0):.0%}")
                if why:
                    st.caption(f"Why it matched: {why}")


# ── Top bar: examples + new chat ────────────────────────────────────────────
picked = None
cols = st.columns([3, 3, 3, 1.4])
for col, text in zip(cols, EXAMPLES):
    if col.button(text, key=f"kb_ex_{text}", width="stretch"):
        picked = text
if cols[3].button("New chat", key="kb_new", icon="🧹", width="stretch", disabled=not chat):
    st.session_state["chat"] = chat = []
    st.rerun()

if not chat:
    ui.empty_state("Type your question below, or click one of the examples above. "
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
