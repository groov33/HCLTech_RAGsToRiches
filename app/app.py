"""ResolveIQ dashboard entry point.

    streamlit run app/app.py        (from the project root)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))      # so "from app import ..." and "from src import ..." work

import streamlit as st  # noqa: E402

from app import backend, state  # noqa: E402

st.set_page_config(page_title="ResolveIQ", page_icon="🎫", layout="wide")
state.init()

PAGES_BY_ROLE = {
    "employee": [st.Page("pages/kb_assistant.py", title="KB Assistant", icon="📚", default=True)],
    "support": [st.Page("pages/new_ticket.py", title="New ticket", icon="🎫", default=True),
                st.Page("pages/past_tickets.py", title="Past tickets", icon="📁")],
    "admin": [st.Page("pages/feedback.py", title="Feedback & audit", icon="💬", default=True),
              st.Page("pages/evaluation.py", title="Evaluation", icon="📊"),
              st.Page("pages/mttr.py", title="MTTR", icon="⏱️"),
              st.Page("pages/knowledge_base.py", title="Knowledge base", icon="📚"),
              st.Page("pages/settings.py", title="Settings", icon="🔑")],
}


@st.cache_data(ttl=30, show_spinner=False)
def _status() -> tuple[dict, dict]:
    return backend.llm_status(), backend.system_status()


with st.sidebar:
    st.markdown("### 🎫 ResolveIQ")
    st.caption("Analyses and recommends. A human always decides.")
    st.selectbox("Viewing as", list(state.ROLES), format_func=state.ROLES.get, key="role",
                 on_change=state.on_role_change)
    st.text_input("Your name", key="analyst", placeholder="e.g. Asha")
    st.caption("Demo role switch — no real sign-in")

nav = st.navigation(PAGES_BY_ROLE[state.role()])

with st.sidebar:
    st.divider()
    llm, sysst = _status()
    active = {"groq": "Groq", "gemini": "Gemini", "ollama": "Ollama (local)"}.get(llm["active"], "none")
    st.caption(f"{'🟢' if llm['active'] else '🔴'} LLM: **{active}**")
    st.caption(f"{'🟢' if sysst['model_file'] else '🔴'} Model file {'loaded' if sysst['model_file'] else 'missing'}")
    st.caption(f"{'🟢' if sysst['search_index'] else '🔴'} Search index {'built' if sysst['search_index'] else 'missing'}")

nav.run()
