"""Shared UI pieces: banners, badges, chips, confidence bars, feedback widget, empty states.

Colours are semi-transparent so they read well in both light and dark themes, and every
coloured element also carries its text (never colour alone).
"""
from __future__ import annotations

import html

import streamlit as st

from app import backend, state

OUTCOME = {  # outcome -> (icon, label, colour, rgb)
    "RECOMMEND": ("✅", "RECOMMEND", "green", "22,163,74"),
    "REVIEW": ("👀", "REVIEW", "orange", "217,119,6"),
    "ESCALATE": ("⬆️", "ESCALATE", "red", "220,38,38"),
    "NEED_INFO": ("❓", "NEED INFO", "blue", "37,99,235"),
}
PRIORITY_COLOR = {"P1": "red", "P2": "orange", "P3": "violet", "P4": "gray"}
PRIORITY_RGB = {"P1": "220,38,38", "P2": "234,88,12", "P3": "202,138,4", "P4": "107,114,128"}
VERDICTS = ["Useful", "Incorrect", "Unresolved"]


def page_header(icon: str, title: str, caption: str) -> None:
    st.title(f"{icon} {title}")
    st.caption(caption)


def show_error(e: Exception) -> None:
    """Friendly error + the command that fixes it. Never a traceback."""
    st.error(str(e))
    if getattr(e, "command", None):
        st.code(e.command, language="bash")


def not_available(title: str, reason: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"Not available yet — {reason}")


def empty_state(message: str) -> None:
    st.info(message, icon="ℹ️")


def badge(text: str, color: str = "blue") -> str:
    """Markdown badge string, for use inside st.markdown."""
    return f":{color}-badge[{text}]"


def priority_badge(p: str) -> str:
    return badge(p, PRIORITY_COLOR.get(p, "gray"))


def outcome_badge(outcome: str) -> str:
    icon, label, color, _ = OUTCOME.get(outcome, ("", outcome, "gray", ""))
    return badge(f"{icon} {label}", color)


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def confidence_bar(value: float, label: str = "Confidence") -> None:
    """Percentage + thin bar. Below 60% amber, below 40% red."""
    rgb = "220,38,38" if value < 0.40 else "217,119,6" if value < 0.60 else "37,99,235"
    st.markdown(
        f"<div style='font-size:0.85rem;opacity:.8'>{html.escape(label)}: <b>{value:.0%}</b></div>"
        f"<div style='height:6px;border-radius:3px;background:rgba(128,128,128,.25);margin:2px 0 8px'>"
        f"<div style='width:{max(2, min(100, value * 100)):.0f}%;height:6px;border-radius:3px;"
        f"background:rgb({rgb})'></div></div>",
        unsafe_allow_html=True)


def outcome_banner(decision: dict) -> None:
    """The big coloured box at the top of a result."""
    icon, label, _, rgb = OUTCOME.get(decision["outcome"], ("", decision["outcome"], "", "107,114,128"))
    reasons = "".join(f"<li>{html.escape(r)}</li>" for r in decision["reasons"])
    extra = ""
    if decision.get("escalate_to"):
        extra = f"<div style='margin-top:6px'>→ hand to <b>{html.escape(decision['escalate_to'])}</b></div>"
    st.markdown(
        f"<div style='border-left:6px solid rgb({rgb});background:rgba({rgb},.12);border-radius:8px;"
        f"padding:14px 18px;margin-bottom:10px'>"
        f"<div style='font-size:1.5rem;font-weight:700'>{icon} {label}"
        f"<span style='font-size:1rem;font-weight:500;opacity:.8'> · confidence {decision['confidence']:.0%}</span></div>"
        f"<ul style='margin:6px 0 0 0'>{reasons}</ul>{extra}</div>",
        unsafe_allow_html=True)
    for q in decision.get("questions") or []:
        st.code(q, language=None)   # st.code has a built-in copy button


def chips(items: list[tuple[str, str]]) -> None:
    """items = [(text, colour)]; renders nothing when empty."""
    if items:
        st.markdown(" ".join(badge(t, c) for t, c in items))


def kpi(col, label: str, value: str, help: str | None = None) -> None:
    with col.container(border=True):
        st.metric(label, value, help=help)


def feedback_widget(analysis_id: str, target_type: str, target_id: str, key: str) -> None:
    """FR-06: Useful / Incorrect / Unresolved + optional comment. Stays editable after saving."""
    k = f"fb_{analysis_id}_{key}"
    c1, c2, c3 = st.columns([3, 4, 1.4], vertical_alignment="bottom")
    verdict = c1.segmented_control("Feedback", VERDICTS, key=f"{k}_v", label_visibility="collapsed")
    comment = c2.text_input("Comment", key=f"{k}_c", placeholder="Optional comment",
                            label_visibility="collapsed")
    if c3.button("Save", key=f"{k}_s", disabled=verdict is None, width="stretch"):
        backend.add_feedback({"analysis_id": analysis_id, "analyst": state.analyst(),
                              "target_type": target_type, "target_id": target_id,
                              "verdict": verdict.lower(), "comment": comment})
        st.toast(f"Saved ✓ — {target_id}: {verdict}")
