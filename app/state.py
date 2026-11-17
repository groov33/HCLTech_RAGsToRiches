"""Session-state keys and the role guard. One place, so pages never invent their own keys."""
import streamlit as st

ROLES = {"employee": "👤 Employee", "support": "🎧 Support", "admin": "⚙️ Admin"}

# Keys that belong to one role's work; cleared when the role changes.
ROLE_SCOPED_KEYS = ("result", "chat", "form", "kb_selected", "audit_selected")


def init() -> None:
    st.session_state.setdefault("role", "support")
    st.session_state.setdefault("analyst", "")


def role() -> str:
    return st.session_state.get("role", "support")


def analyst() -> str:
    return (st.session_state.get("analyst") or "").strip() or "anonymous"


def on_role_change() -> None:
    """Widget callback: switching role wipes the previous role's results and chat."""
    for k in list(st.session_state.keys()):
        if k in ROLE_SCOPED_KEYS or str(k).startswith(("fb_", "nt_", "kb_", "pt_", "au_")):
            del st.session_state[k]


def require_role(*allowed: str) -> None:
    """Second line of defence: the menu already hides other roles' pages; this blocks direct URLs."""
    if role() not in allowed:
        st.error("This page isn't available for your role.")
        st.stop()
