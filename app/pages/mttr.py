"""⏱️ MTTR (Admin, FR-09): simulated manual baseline vs time-to-resolve with ResolveIQ.

Numbers come from backend.get_mttr() (audit log in SQLite) and backend.BASELINE_MIN.
The baseline is SIMULATED and labelled so everywhere.
"""
from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from app import backend, state, ui

state.require_role("admin")
ui.page_header("⏱️", "MTTR",
               "Mean time to resolve: how long tickets take with the assistant, against a simulated manual baseline.")

BASELINE = getattr(backend, "BASELINE_MIN", {}) or {}
SIM = "Simulated baseline"
ASSISTED = "With ResolveIQ"


def _dur(minutes) -> str:
    """Minutes -> '45 s' / '12 min' / '4 h' / '1 day' / '2.5 days'. '—' for None."""
    if not isinstance(minutes, (int, float)):
        return "—"
    if minutes < 1:
        return f"{minutes * 60:.0f} s"
    if minutes < 60:
        return f"{minutes:.0f} min"
    if minutes < 1440:
        h = minutes / 60
        return f"{h:.0f} h" if h == int(h) else f"{h:.1f} h"
    d = minutes / 1440
    return f"{d:.0f} day{'s' if d != 1 else ''}" if d == int(d) else f"{d:.1f} days"


def _minutes(start, end):
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
    except (TypeError, ValueError):
        return None


assumption = ", ".join(f"{p} {_dur(m)}" for p, m in BASELINE.items()) or "not set"
st.info(f"**{SIM}:** our data has no real resolution history, so manual handling time per priority is assumed "
        f"({assumption}). Assisted time = 'Mark resolved' time − ticket submitted time, from the audit log.",
        icon="🧪")

# ── load ────────────────────────────────────────────────────────────────────
try:
    report = backend.get_mttr() or {}
except Exception as e:  # noqa: BLE001 - friendly message, never a traceback
    print(f"[mttr] get_mttr failed: {type(e).__name__}: {str(e)[:200]}")
    ui.not_available("MTTR", "the audit log could not be read (src/store.py / data/store/resolveiq.db).")
    st.stop()

try:
    audit = backend.get_audit({}) or []
except Exception as e:  # noqa: BLE001
    print(f"[mttr] get_audit failed: {type(e).__name__}: {str(e)[:200]}")
    audit = []

rows = [r for r in (report.get("rows") or []) if isinstance(r, dict)]
n_resolved = sum(int(r.get("n_resolved") or 0) for r in rows)
reduction = report.get("overall_reduction_pct")

# Time to recommendation over every stored analysis (display-only average of audit timestamps).
to_rec = [m for m in (_minutes((a.get("timestamps") or {}).get("created_at"),
                               (a.get("timestamps") or {}).get("recommended_at")) for a in audit)
          if m is not None]

# ── KPIs ────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
ui.kpi(c1, "Overall time reduction", f"{reduction:.1f}%" if isinstance(reduction, (int, float)) else "—",
       help=f"1 − (total assisted minutes ÷ total {SIM.lower()} minutes), over resolved tickets only. "
            "Shows '—' until at least one ticket is marked resolved.")
ui.kpi(c2, "Tickets resolved with the assistant", str(n_resolved),
       help="Analyses where someone clicked 'Mark resolved' on New ticket.")
ui.kpi(c3, "Avg time to recommendation", _dur(sum(to_rec) / len(to_rec)) if to_rec else "—",
       help=f"Ticket submitted → recommendation shown, averaged over {len(to_rec)} stored analyses.")
ui.kpi(c4, "Analyses in the audit log", str(len(audit)),
       help="Every analysed ticket is stored; only the ones marked resolved count towards MTTR.")

if not rows:
    ui.not_available("MTTR by priority", "no rows returned by backend.get_mttr().")
    st.stop()

if n_resolved == 0:
    ui.empty_state("No resolved tickets yet — analyse a ticket on New ticket (Support) and click Mark resolved.")

# ── chart: baseline vs assisted per priority ────────────────────────────────
if n_resolved:
    st.subheader("Baseline vs assisted, per priority")
    chart_rows = []
    for r in rows:
        p = r.get("priority")
        base, assisted, n = r.get("baseline_min"), r.get("assisted_min"), int(r.get("n_resolved") or 0)
        if isinstance(base, (int, float)) and base > 0:
            chart_rows.append({"Priority": p, "Series": SIM, "Hours": base / 60, "Time": _dur(base), "Label": ""})
        if isinstance(assisted, (int, float)) and assisted > 0:
            chart_rows.append({"Priority": p, "Series": ASSISTED, "Hours": assisted / 60, "Time": _dur(assisted),
                               "Label": f"n={n}"})
    if chart_rows:
        cdf = pd.DataFrame(chart_rows)
        order = [r.get("priority") for r in rows]
        enc = dict(
            x=alt.X("Priority:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("Series:N", sort=[SIM, ASSISTED]),
            y=alt.Y("Hours:Q", scale=alt.Scale(type="log"), title="Hours (log scale)"),
        )
        bars = alt.Chart(cdf).mark_bar(cornerRadiusEnd=2).encode(
            **enc,
            color=alt.Color("Series:N", sort=[SIM, ASSISTED], title=None, legend=alt.Legend(orient="bottom"),
                            scale=alt.Scale(domain=[SIM, ASSISTED], range=["#8B95A5", "#2563EB"])),
            opacity=alt.condition(alt.datum.Series == SIM, alt.value(0.75), alt.value(1.0)),
            tooltip=["Priority", "Series", "Time", alt.Tooltip("Label:N", title="Resolved tickets")],
        )
        labels = alt.Chart(cdf[cdf["Label"] != ""]).mark_text(dy=-8, fontWeight="bold").encode(
            **enc, text="Label:N", color=alt.value("#2563EB"))
        st.altair_chart((bars + labels).properties(height=340), width="stretch")
        st.caption("Log scale, because assisted times can be minutes while the baseline is hours or days. "
                   "**n** = resolved tickets behind each blue bar — small samples are noisy.")

# ── table ───────────────────────────────────────────────────────────────────
st.subheader("By priority")
table = []
for r in rows:
    base, assisted = r.get("baseline_min"), r.get("assisted_min")
    red = (f"{100 * (1 - assisted / base):.1f}%"
           if isinstance(base, (int, float)) and base and isinstance(assisted, (int, float)) else "—")
    table.append({"Priority": r.get("priority"), SIM: _dur(base), "Assisted (avg)": _dur(assisted),
                  "Time to recommendation (avg)": _dur(r.get("to_recommendation_min")),
                  "Resolved tickets (n)": int(r.get("n_resolved") or 0), "Reduction": red})
st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")

# ── optional: by category (from the audit log) ─────────────────────────────
resolved = []
for a in audit:
    ts, lab = a.get("timestamps") or {}, a.get("classification") or {}
    m = _minutes(ts.get("created_at"), ts.get("resolved_at"))
    if m is not None:
        resolved.append({"Category": lab.get("category") or "—", "assisted": m,
                         "baseline": BASELINE.get(lab.get("priority"))})
if resolved:
    with st.expander("By category"):
        df = pd.DataFrame(resolved)
        out = []
        for cat, g in df.groupby("Category"):
            base = g["baseline"].dropna()
            red = (f"{100 * (1 - g.loc[base.index, 'assisted'].sum() / base.sum()):.1f}%"
                   if len(base) and base.sum() else "—")
            out.append({"Category": cat, "Resolved tickets (n)": len(g), "Assisted (avg)": _dur(g["assisted"].mean()),
                        f"{SIM} (avg)": _dur(base.mean()) if len(base) else "—", "Reduction": red})
        st.dataframe(pd.DataFrame(out), hide_index=True, width="stretch")
        st.caption(f"{SIM} per ticket = the assumed time for that ticket's predicted priority.")
