"""Data contracts between the pipeline and the dashboard.

One place that says what every pipeline step hands over, and what the
dashboard reads. Both sides import these names, so a renamed field shows up
as a type error instead of a blank card on demo day.

They are TypedDicts (plain dicts at runtime): src/classify.py already returns
dicts, so nothing has to be rewritten, and no extra dependency is needed.

Flow of contracts (step numbers = Docs/PROJECT_OVERVIEW.md §4):

    TicketInput ─2─> CleanedTicket ─4─> SimilarTicketsResult ─3,5,6─> Classification
        ─5b─> Tiebreak ─7─> KBSearchResult ─8─> Fix ─9─> Decision
    all of the above ──> AnalysisResult ──> dashboard (New ticket page, audit log)
"""
from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

CONTRACT_VERSION = "1.0"

Role = Literal["employee", "support", "admin"]   # employee → KB Assistant · support → tickets · admin → admin pages
Outcome = Literal["RECOMMEND", "REVIEW", "ESCALATE", "NEED_INFO"]
Priority = Literal["P1", "P2", "P3", "P4"]
Level = Literal["High", "Medium", "Low"]
LLMName = Literal["groq", "gemini", "ollama"]
Verdict = Literal["useful", "incorrect", "unresolved"]
PipelinePart = Literal["retrieve", "llm", "resolve", "decide", "store"]


# ── Step 1 · Ticket form → pipeline ─────────────────────────────────────────
class TicketInput(TypedDict):
    description: str
    service: str                 # key of taxonomy.SERVICES        (trusted)
    environment: str             # taxonomy.ENVIRONMENTS           (trusted)
    who_affected: str            # taxonomy.WHO_AFFECTED           (trusted)
    user_category: str           # user's guess, may be wrong
    user_subcategory: str        # must belong to user_category
    ticket_id: NotRequired[str]  # present for dataset tickets (e.g. INC-00156)


# ── Step 2 · Clean text ─────────────────────────────────────────────────────
class CleanedTicket(TypedDict):
    masked_description: str      # PII hidden; the only description the UI/LLM/export ever sees
    clean_text: str              # masked + hype sentences removed + lowercased (model/search input)
    hype_detected: bool
    too_vague: bool              # completeness check → NEED INFO


# ── Step 4 · Similar past tickets + vote ────────────────────────────────────
class SimilarTicket(TypedDict):
    ticket_id: str
    excerpt: str                 # PII-masked
    score: float                 # 0–1, merged vector + keyword
    category: str
    subcategory: str
    priority: Priority
    why_matched: list[str]       # e.g. ["same service: VPN", "keyword: 'drive'"]
    is_duplicate: bool           # score above tuned threshold = "same problem seen before"


class Vote(TypedDict):
    category: str                # majority category of the top 5 → classify(similar_vote=...)
    agree_count: int
    of: int


class SimilarTicketsResult(TypedDict):
    tickets: list[SimilarTicket]  # top 5
    vote: Vote | None             # None when no similar tickets


# ── Steps 3, 5, 6 · Classification  (= TicketClassifier.predict() output) ───
class TopItem(TypedDict):
    label: str
    prob: float


class Confidence(TypedDict):
    category: float
    subcategory: float
    symptom_type: float
    category_score: float        # 0.6·model + 0.2·vote agrees + 0.2·user agrees


class Top3(TypedDict):
    category: list[TopItem]
    subcategory: list[TopItem]
    symptom_type: list[TopItem]


class Classification(TypedDict):
    category: str
    subcategory: str
    symptom_type: str
    team: str
    impact: Level
    urgency: Level
    priority: Priority
    priority_reason: str         # one plain sentence from rules.explain_priority
    confidence: Confidence
    top3: Top3
    user_category: str | None
    user_agrees: bool | None
    hype_detected: bool
    possible_security: bool      # security safety net
    needs_review: bool
    review_reasons: list[str]


# ── Step 5b · LLM tiebreak (only when category_score < 0.75) ────────────────
class Tiebreak(TypedDict):
    used: bool
    candidates: list[str]        # top 2–3 the LLM had to choose from
    chosen: str | None           # None if both LLMs failed → best-scoring label kept
    reason: str
    llm: LLMName | None


# ── Step 7 · KB articles ────────────────────────────────────────────────────
class KBStep(TypedDict):
    step_id: str                 # "KB-005/support/1" or "KB-005/self/2"
    text: str


class KBHit(TypedDict):
    kb_id: str
    title: str
    subcategory: str
    access_level: Literal["public", "internal"]
    score: float                 # 0–1
    why_matched: list[str]
    steps: list[KBStep]          # already role-filtered (employees: self-help only)
    verify: str
    escalate_when: str


class KBSearchResult(TypedDict):
    articles: list[KBHit]        # top 3, role-filtered BEFORE search
    best_score: float            # → knowledge gap if below threshold
    conflict: bool               # #1 and #2 close but different subcategories
    knowledge_gap: bool


# ── Step 8 · Fix written by the LLM, after citation check ───────────────────
class FixStep(TypedDict):
    text: str
    cites: list[str]             # step_ids
    source_quote: str            # the cited KB text, shown when a chip is clicked


class FixPath(TypedDict):
    kb_id: str
    title: str
    why_it_fits: str
    steps: list[FixStep]         # only steps that PASSED the citation check


class Fix(TypedDict):
    paths: list[FixPath]
    citation_validity: float     # kept / written
    dropped_steps: int
    llm: LLMName
    clarifying_questions: list[str]


# ── Step 9 · Decision ───────────────────────────────────────────────────────
class Decision(TypedDict):
    outcome: Outcome
    confidence: float            # mean(category_score, kb best_score, citation_validity)
    reasons: list[str]           # plain sentences, always ≥ 1
    questions: list[str]         # NEED_INFO only
    escalate_to: str | None      # team, ESCALATE only


# ── Cross-cutting ───────────────────────────────────────────────────────────
class TraceStep(TypedDict):
    step: str                    # "1".."9", "5b"
    name: str
    ms: float
    detail: str                  # key output in one line, e.g. "Account & Access 0.88"
    status: Literal["done", "skipped", "missing", "failed"]


class Timestamps(TypedDict):
    created_at: str              # ISO 8601, form submitted
    recommended_at: str | None   # result ready
    resolved_at: str | None      # analyst clicked "Mark resolved"


# ── The whole result: pipeline → dashboard + audit log ──────────────────────
class AnalysisResult(TypedDict):
    contract_version: str
    analysis_id: str             # "AN-YYYYMMDD-NNNN"
    analyst: str
    role: Role
    ticket: TicketInput          # description replaced by masked_description
    cleaned: CleanedTicket
    similar: SimilarTicketsResult | None     # None = retrieve not built / failed
    classification: Classification
    tiebreak: Tiebreak | None                # None = not needed
    kb: KBSearchResult | None
    fix: Fix | None                          # None = LLM unavailable, knowledge gap, or not built
    decision: Decision
    trace: list[TraceStep]
    timestamps: Timestamps
    missing_parts: list[PipelinePart]        # parts not built yet; UI shows "not available yet"


# ── KB Assistant ────────────────────────────────────────────────────────────
class KBAnswer(TypedDict):
    question: str
    answered: bool               # False → "not in the knowledge base, raise a ticket"
    steps: list[FixStep]
    sources: list[KBHit]
    llm: LLMName | None


# ── Feedback, audit, MTTR, status (Admin pages) ─────────────────────────────
class FeedbackRecord(TypedDict):
    feedback_id: str
    analysis_id: str
    analyst: str
    target_type: Literal["classification", "similar_ticket", "kb_article", "fix"]
    target_id: str               # e.g. "category", "INC-00412", "KB-005", "fix"
    verdict: Verdict
    comment: str
    created_at: str


class MTTRRow(TypedDict):
    priority: Priority
    baseline_min: float          # SIMULATED manual handling time
    assisted_min: float | None   # None until ≥ 1 resolved
    to_recommendation_min: float | None
    n_resolved: int


class MTTRReport(TypedDict):
    rows: list[MTTRRow]
    overall_reduction_pct: float | None
    baseline_is_simulated: bool  # always True for our data; UI must label it


class LLMStatus(TypedDict):
    groq: Literal["ok", "no key", "error"]
    gemini: Literal["ok", "no key"]   # "ok" = at least one key configured (not tested, to save quota)
    ollama: Literal["ok", "down"]
    active: LLMName | None


class SystemStatus(TypedDict):
    model_file: bool
    search_index: bool
    modules: dict[str, bool]     # "src/retrieve.py" → built?
    build_commands: dict[str, str]


# ── Light runtime check (used by the dashboard and tests) ───────────────────
_REQUIRED_RESULT_KEYS = set(AnalysisResult.__annotations__)


def check_result(result: dict) -> list[str]:
    """Return a list of problems (empty = OK). Cheap, so the UI can call it on every result."""
    problems = [f"missing key: {k}" for k in sorted(_REQUIRED_RESULT_KEYS - result.keys())]
    if result.get("contract_version") != CONTRACT_VERSION:
        problems.append(f"contract_version {result.get('contract_version')!r} != {CONTRACT_VERSION!r}")
    cls = result.get("classification") or {}
    problems += [f"classification missing: {k}" for k in sorted(set(Classification.__annotations__) - cls.keys())]
    if (result.get("decision") or {}).get("outcome") == "RECOMMEND" and not result.get("fix"):
        problems.append("RECOMMEND without a cited fix is not allowed")
    return problems
