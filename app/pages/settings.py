"""🔑 Settings (Admin): Groq key and model, Ollama status, which LLM is active, and what is built."""
import pandas as pd
import streamlit as st

from app import backend, state, ui

state.require_role("admin")
ui.page_header("🔑", "Settings",
               "Connect the language model that writes fixes, and check which parts of the system are built.")

GROQ_MSG = {
    "ok": ("✅", "Groq is connected."),
    "no key": ("❌", "No Groq API key is set. Paste one below to use Groq."),
    "error": ("❌", "Groq rejected the key or can't be reached. Check the key and your internet connection."),
}


def save_key() -> None:
    """Button callback: use the key, then clear the box. The key itself is never shown or put in a message."""
    key = (st.session_state.get("se_key") or "").strip()
    st.session_state["se_key"] = ""
    if not key:
        st.session_state["se_msg"] = ("warning", "Paste a key first.")
        return
    try:
        status = backend.set_api_key(key, bool(st.session_state.get("se_remember")))
    except Exception as e:  # noqa: BLE001 - message must never contain the key
        print(f"[settings] saving the Groq key failed: {type(e).__name__}")
        st.session_state["se_msg"] = ("error", "Couldn't save the key (the .env file may be read-only). "
                                               "It was not stored.")
        return
    st.cache_data.clear()
    icon, text = GROQ_MSG[status["groq"]]
    saved = " Saved to .env on this machine." if st.session_state.get("se_remember") else " Kept for this session only."
    st.session_state["se_msg"] = ("success" if status["groq"] == "ok" else "error", f"{icon} {text}{saved}")


def save_model() -> None:
    try:
        backend.set_groq_model(st.session_state["se_model"], bool(st.session_state.get("se_model_remember")))
    except Exception as e:  # noqa: BLE001
        print(f"[settings] saving the Groq model failed: {type(e).__name__}")
        st.session_state["se_model_msg"] = ("error", "Couldn't save the model choice to .env.")
        return
    st.cache_data.clear()
    st.session_state["se_model_msg"] = ("success", f"Groq model set to {st.session_state['se_model']}.")


def show_msg(key: str) -> None:
    msg = st.session_state.pop(key, None)
    if msg:
        getattr(st, msg[0])(msg[1])


try:
    llm = backend.llm_status()
    models = backend.llm_models()
except Exception as e:  # noqa: BLE001
    print(f"[settings] llm status failed: {type(e).__name__}")
    llm, models = {"groq": "error", "ollama": "down", "active": None}, backend.llm_models()

# ── Active LLM ──────────────────────────────────────────────────────────────
active = {"groq": ("🟢", "Groq"), "ollama": ("🟡", "Ollama (Groq unavailable)")}.get(
    llm["active"], ("🔴", "None: fixes can't be written; tickets will be escalated"))
with st.container(border=True):
    st.markdown(f"**Active LLM:** {active[0]} {active[1]}")
    st.caption("Groq is tried first; if it isn't available the local Ollama model is used.")

c1, c2 = st.columns(2)

# ── Groq ────────────────────────────────────────────────────────────────────
with c1.container(border=True):
    st.markdown("#### Groq (cloud)")
    icon, text = GROQ_MSG[llm["groq"]]
    st.markdown(f"{icon} {text}")
    current = backend.masked_key()
    st.caption(f"Current key: `{current}`" if current else "Current key: none")

    st.text_input("Groq API key", type="password", key="se_key", placeholder="gsk_…",
                  help="Shown only masked after saving. Never logged or written to the audit log.")
    st.checkbox("Remember on this machine (writes to .env)", key="se_remember",
                help=".env is git-ignored. Leave unticked to keep the key for this session only.")
    st.button("Save & test connection", key="se_save", type="primary", on_click=save_key)
    show_msg("se_msg")

    st.divider()
    options = list(backend.GROQ_MODELS)
    if models["groq_model"] not in options:
        options.append(models["groq_model"])
    st.selectbox("Groq model", options, index=options.index(models["groq_model"]), key="se_model",
                 help="The 70b model writes better fixes; the 8b model is faster.")
    st.checkbox("Remember model choice (writes to .env)", key="se_model_remember")
    st.button("Save model", key="se_model_save", on_click=save_model)
    show_msg("se_model_msg")

# ── Ollama ──────────────────────────────────────────────────────────────────
with c2.container(border=True):
    st.markdown("#### Ollama (local)")
    if llm["ollama"] == "ok":
        st.markdown(f"✅ Ollama is running at `{models['ollama_url']}`.")
    else:
        st.markdown(f"❌ Ollama isn't reachable at `{models['ollama_url']}`.")
        st.caption("Start it, then download the model once:")
        st.code(f"ollama serve\nollama pull {models['ollama_model']}", language="bash")
    st.markdown(f"Model: `{models['ollama_model']}`")
    st.caption("Set with the OLLAMA_MODEL and OLLAMA_URL environment variables. The local model is slower "
               "(10–60 s per answer) but works without internet.")
    if st.button("Re-check status", key="se_recheck"):
        st.cache_data.clear()
        st.rerun()

# ── System status ───────────────────────────────────────────────────────────
st.subheader("System status")
try:
    sysst = backend.system_status()
except Exception as e:  # noqa: BLE001
    print(f"[settings] system status failed: {type(e).__name__}")
    sysst = None

if sysst is None:
    st.error("Couldn't check the system status. Check the console for details.")
else:
    cmds = sysst.get("build_commands", {})
    rows = [{"Part": "Model file (classifier)", "Status": sysst["model_file"],
             "How to build": cmds.get("model file", "")},
            {"Part": "Search index", "Status": sysst["search_index"],
             "How to build": cmds.get("search index", "")}]
    rows += [{"Part": m, "Status": ok, "How to build": f"Not built yet — {m}"}
             for m, ok in sysst.get("modules", {}).items()]
    df = pd.DataFrame(rows)
    df.loc[df["Status"], "How to build"] = ""
    df["Status"] = df["Status"].map({True: "✅ built", False: "❌ missing"})
    st.dataframe(df, hide_index=True, width="stretch")

    missing = [r for r in rows if not r["Status"]]
    if missing:
        st.warning(f"{len(missing)} part(s) missing. Run the command shown next to each one from the project root.")
    else:
        st.success("Everything is built.")
    with st.expander("Other build commands"):
        for name, cmd in cmds.items():
            st.markdown(f"**{name.capitalize()}**")
            st.code(cmd, language="bash")
