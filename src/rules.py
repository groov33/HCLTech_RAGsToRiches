"""Deterministic rules: team, impact, urgency, priority.

These use only trusted facts (service, environment, who_affected) plus the
PREDICTED category and symptom_type. Nothing here reads the tone of the text.
"""
import calendar
from datetime import date, timedelta

from .taxonomy import SERVICES

PRIORITY_MATRIX = {
    ("High", "High"): "P1", ("High", "Medium"): "P2", ("High", "Low"): "P3",
    ("Medium", "High"): "P2", ("Medium", "Medium"): "P3", ("Medium", "Low"): "P4",
    ("Low", "High"): "P3", ("Low", "Medium"): "P4", ("Low", "Low"): "P4",
}


def is_critical(service: str) -> bool:
    return SERVICES.get(service, ("Minor", ""))[0] == "Critical"


def _last_working_days(year: int, month: int, n: int = 3) -> set[date]:
    d = date(year, month, calendar.monthrange(year, month)[1])
    days = set()
    while len(days) < n:
        if d.weekday() < 5:            # Mon-Fri
            days.add(d)
        d -= timedelta(days=1)
    return days


def in_busy_period(service: str, when: date | None) -> bool:
    """Finance: last 3 working days of the month. Payroll: 25th-30th."""
    if when is None:
        return False
    if service == "Finance System":
        return when in _last_working_days(when.year, when.month)
    if service == "Payroll System":
        return 25 <= when.day <= 30
    return False


def team(category: str, service: str) -> str:
    if category == "Security":
        return "Security"
    if category == "Account & Access":
        return "Service Desk"
    return SERVICES.get(service, ("Minor", "Service Desk"))[1]


def impact(who_affected: str, service: str, category: str, symptom_type: str) -> str:
    critical = is_critical(service)
    if who_affected in ("Many teams", "Customers") or category == "Security" or (critical and symptom_type == "outage"):
        return "High"
    if who_affected == "My team" or (critical and symptom_type == "blocked"):
        return "Medium"
    return "Low"


def urgency(environment: str, service: str, category: str, symptom_type: str, when: date | None = None) -> str:
    if category == "Security":
        return "High"
    if symptom_type in ("request", "question"):
        return "Low"
    if symptom_type in ("outage", "blocked") and environment == "Production":
        return "High"
    if in_busy_period(service, when):
        return "High"
    return "Medium"


def priority(impact_level: str, urgency_level: str) -> str:
    return PRIORITY_MATRIX[(impact_level, urgency_level)]


def explain_priority(impact_level, urgency_level, who_affected, service, environment, symptom_type, busy):
    """One plain sentence a judge or analyst can read."""
    p = priority(impact_level, urgency_level)
    importance = SERVICES.get(service, ("Minor", ""))[0].lower()
    busy_txt = ", busy period" if busy else ""
    return (f"{p}: impact {impact_level} ({who_affected.lower()}, {importance} service) "
            f"x urgency {urgency_level} ({symptom_type}, {environment.lower()}{busy_txt}).")
