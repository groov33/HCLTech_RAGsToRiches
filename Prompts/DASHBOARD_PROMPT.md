# Prompt — Build the ResolveIQ Dashboard (Streamlit)

> Give this whole file to an AI coding assistant working **inside this repository**. It is written as instructions to that assistant.

---

## 0. Your role and goal

You are a senior Python + Streamlit engineer. Build the **ResolveIQ dashboard**: the user interface of an *Intelligent IT Ticket Analysis and Resolution Assistant* for an HCLTech hackathon. Judges will use it live. It must be:
- **clear**: a non-expert understands every screen in 5 seconds,
- **honest**: every number has a source, and simulated or generated data says so,
- **traceable**: every label, match and fix step shows *why*,
- **safe**: it analyses and recommends only; a human always decides.

### Read these first (in this order) and treat them as the source of truth
1. `Docs/PROJECT_OVERVIEW.md`: the whole system, the 9-step pipeline, decision rules, brief coverage, demo script
2. `Docs/HLD.md`: layers, components, data model
3. `Docs/RAG_PLAN.md`: search, fix writing, citations
4. `Problem Statement/PROBLEM_STATEMENT.md`: the brief (FR-01 … FR-09)
5. **`src/contracts.py`**: the data contracts between the pipeline and the dashboard (§3). **Every shape you use comes from here**
6. `src/taxonomy.py`, `src/classify.py`, `src/rules.py`, `src/text.py`: **existing code you must reuse, not rewrite**
7. `reports/eval_results.json`, `reports/*.png`: existing evaluation output

If this prompt and those docs disagree, **the docs win**. Tell me about the conflict.

---

## 1. Hard rules (never break these)

1. **The UI never contains business logic.** Pages call `app/backend.py` only. The backend calls `src/*`. No classification, priority, search or LLM code inside a page.
2. **Reuse the fixed lists** from `src/taxonomy.py` (`SERVICES`, `ENVIRONMENTS`, `WHO_AFFECTED`, `CATEGORIES`, `TEAMS`, `SYMPTOM_TYPES`). Never hard-code option lists in pages.
3. **No action on real systems.** There is no "close ticket", "apply fix" or "run command" button anywhere. The only actions are *analyse*, *give feedback*, *mark resolved* and *export*.
4. **Each role sees only its own pages** (see §4): Employee → KB Assistant · Support → New ticket, Past tickets · Admin → Feedback, Evaluation, MTTR, Knowledge base, Settings.
   - The KB Assistant uses only public articles and self-help steps. This filter is applied in the backend **before** search, not by hiding things in the UI.
5. **Hide personal data in everything shown or exported:** emails, phone numbers, employee IDs, using the same masking as `src/text.py` (add a `mask_pii()` there if it doesn't exist).
6. **API key safety:**
   - The Groq key is entered in a password field and shown only as `gsk_••••abcd`.
   - It is never printed, logged, put in an error message or written to the audit log.
   - It is stored in `st.session_state`, and written to `.env` (already git-ignored) only if the admin ticks "remember on this machine".
7. **Label all simulated or generated data on screen**: MTTR baseline = "Simulated baseline", dataset labels = "Generated labels".
8. **Never show a fake result as real.** Anything not built yet must show a clear "Not available yet — `<file>` not built" state, never invented numbers.
9. **Plain language.** "Similar past tickets", not "kNN neighbours". "Confidence", not "posterior". Technical detail goes in expanders and the Trace tab.
10. **No new heavy dependencies.** Use Streamlit's built-in charts or Altair (ships with Streamlit). Add only `streamlit>=1.40` to `requirements.txt`, plus `python-dotenv` if you write `.env`.

---

## 2. What the app sits on (context)

### The 9-step pipeline (one call per ticket)
| # | Step | Done by | Shown in UI as |
|---|---|---|---|
| 1 | Ticket form | user | the form |
| 2 | Clean text: hide personal data, drop hype | rules (`src/text.py`) | "Hype detected (ignored for priority)" chip |
| 3 | Classify category, subcategory, symptom type | ML, 3 logistic regressions | label + confidence bar + top-3 |
| 4 | Similar past tickets + vote | vector + keyword search | Similar tickets tab |
| 5 | Combined score `0.6·model + 0.2·vote agrees + 0.2·user agrees`, threshold 0.75 | Python | score + "user chose X, model says Y" chip |
| 5b | LLM tiebreak (only if < 0.75) | Groq → Ollama | "Tiebreak used" chip + LLM's reason |
| 6 | Team, impact, urgency, priority | rules + ITIL matrix, **no LLM** | priority badge + one-sentence reason |
| 7 | Find KB articles (role-filtered) | vector + keyword search | KB articles tab |
| 8 | Write fix, every step cited, citation check | LLM + `rapidfuzz` | Recommended fix tab |
| 9 | Decide | rules | the big outcome banner |

### Outcomes (step 9)
| Outcome | Colour | Meaning |
|---|---|---|
| ✅ RECOMMEND | green | evidence strong and consistent |
| 👀 REVIEW | amber | probably right, check before acting |
| ⬆️ ESCALATE | red | P1/P2, knowledge gap, or LLM unavailable: a human team owns it |
| ❓ NEED INFO | blue | too vague, so ask the user 1–2 questions |

**Security safety net:** if `possible_security` is true, always show a red chip *"Possible security issue — check with Security team"*, whatever the outcome.

---

## 3. The integration contract (`app/backend.py`)

Pages talk only to these functions. Implement them on top of the real `src/` modules.

```python
from src.contracts import (TicketInput, AnalysisResult, KBAnswer, KBHit, FeedbackRecord,
                           MTTRReport, LLMStatus, SystemStatus, Role, Verdict, check_result)

def analyze_ticket(ticket: TicketInput, role: Role, analyst: str) -> AnalysisResult
def list_tickets(filters: dict, role: Role) -> pd.DataFrame          # Past tickets (PII masked)
def get_ticket(ticket_id: str, role: Role) -> dict
def ask_kb(question: str, role: Role) -> KBAnswer
def list_kb(filters: dict, role: Role) -> list[KBHit]
def add_feedback(record: FeedbackRecord) -> None
def mark_resolved(analysis_id: str) -> None                          # sets timestamps.resolved_at
def get_feedback(analyst: str | None = None) -> list[FeedbackRecord]
def get_audit(filters: dict) -> list[AnalysisResult]
def export_audit(filters: dict, fmt: str) -> bytes                   # "csv" | "json", PII masked
def get_mttr() -> MTTRReport
def get_eval() -> dict | None                                        # reads reports/eval_results.json as-is
def llm_status() -> LLMStatus
def set_api_key(key: str, remember: bool) -> LLMStatus               # tests the key
def system_status() -> SystemStatus
```

### 3.1 The contracts: `src/contracts.py` is the single source of truth

Every message between the pipeline and the dashboard is defined once in **`src/contracts.py`** as a `TypedDict` (a plain dict at runtime, so there's no new dependency). **Import those names. Don't redefine shapes in the app.**
- If you need a field that isn't there, add it to `src/contracts.py`, bump `CONTRACT_VERSION`, and tell me.
- Call `check_result(result)` on every `AnalysisResult`. If it returns problems, show them in an expander "Contract warnings" on the Trace tab, never as a crash.

**What each pipeline step produces:**

| Step | Producer (module) | Contract out | Inside `AnalysisResult` at | `None` when |
|---|---|---|---|---|
| 1 Form | `app/pages/new_ticket.py` | `TicketInput` | `ticket` (description masked) | never |
| 2 Clean | `src/text.py` | `CleanedTicket` | `cleaned` | never |
| 4 Similar tickets | `src/retrieve.py` | `SimilarTicketsResult` (+ `Vote`) | `similar` | retrieve not built / failed |
| 3, 5, 6 Classify + score + priority | `src/classify.py` (`TicketClassifier.predict(ticket, similar_vote=vote.category)`) | `Classification` (**exact** existing output, verified key-for-key) | `classification` | never |
| 5b Tiebreak | `src/classify.py` + `src/llm.py` | `Tiebreak` | `tiebreak` | not needed (score ≥ 0.75) |
| 7 KB search | `src/retrieve.py` | `KBSearchResult` (list of `KBHit`) | `kb` | retrieve not built |
| 8 Write fix | `src/resolve.py` + `src/llm.py` | `Fix` (only steps that passed the citation check) | `fix` | LLM down, knowledge gap, not built |
| 9 Decide | `src/decide.py` | `Decision` | `decision` | never |
| all | `src/pipeline.py` | `TraceStep[]`, `Timestamps`, `missing_parts` | `trace`, `timestamps`, `missing_parts` | never |

**Real example:** `Classification` for INC-00156, produced by today's trained model with no similar-ticket vote yet:

```json
{"category": "Account & Access", "subcategory": "Account locked", "symptom_type": "blocked",
 "team": "Service Desk", "impact": "Medium", "urgency": "High", "priority": "P2",
 "confidence": {"category": 0.968, "subcategory": 0.797, "symptom_type": 0.986, "category_score": 0.726},
 "user_category": "Device & Software", "user_agrees": false, "hype_detected": true,
 "needs_review": true,
 "review_reasons": ["user chose 'Device & Software', model says 'Account & Access'"], "...": "..."}
```

### 3.2 What the dashboard reads (field → widget)

Build each widget from **only** the fields listed here. If the field is `None` or the parent block is `None`, show the "not available" state in the last column.

| Page › widget | Reads | If missing / `None` |
|---|---|---|
| New ticket › outcome banner | `decision.outcome`, `.confidence`, `.reasons`, `.escalate_to`, `.questions` | (never missing) |
| › chip "Hype ignored" | `classification.hype_detected` | hide |
| › chip "You chose X, model says Y" | `classification.user_agrees == False`, `.user_category`, `.category` | hide |
| › chip "Possible security issue" | `classification.possible_security` | hide |
| › chip "LLM tiebreak used" | `tiebreak.used`, `.chosen`, `.reason`, `.llm` | hide |
| › chip "Knowledge gap" | `kb.knowledge_gap` | hide |
| › Category / Subcategory / Symptom cards | `classification.<field>`, `.confidence.<field>`, `.top3.<field>` | (never missing) |
| › combined score line | `classification.confidence.category_score`, `.review_reasons` | (never missing) |
| › Priority card | `classification.priority`, `.priority_reason`, `.team`, `.impact`, `.urgency` | (never missing) |
| › Recommended fix tab | `fix.paths[].{title, why_it_fits, steps[].{text, cites, source_quote}}`, `fix.citation_validity`, `fix.dropped_steps`, `fix.llm`; `kb.articles[].{verify, escalate_when}` | grey card with the reason: "LLM unavailable" (`decision.reasons`), "Knowledge gap", or "`src/resolve.py` not built" (`missing_parts`) |
| › Similar tickets tab | `similar.tickets[]` (all fields), `similar.vote` | "not available yet (`src/retrieve.py`)" |
| › KB articles tab | `kb.articles[]` (all fields), `kb.conflict` | same |
| › Trace tab | `trace[]`, `missing_parts`, `contract_version`, `check_result()` output | (never missing) |
| › Audit record tab | the whole `AnalysisResult` (already masked) | (never missing) |
| › feedback widgets | `analysis_id` + target id (`"category"`, `similar.tickets[].ticket_id`, `kb.articles[].kb_id`, `"fix"`) → writes `FeedbackRecord` | — |
| › Mark resolved | `analysis_id`, `timestamps.*` | — |
| KB Assistant | `KBAnswer.{answered, steps, sources, llm}` | `answered == False` → "raise a ticket" message |
| Past tickets | `list_tickets()` DataFrame: ticket fields from the dataset (`ticket_id, description (masked), service, environment, who_affected, user_category, user_subcategory, category, subcategory, symptom_type, team, impact, urgency, priority`) | empty-filter message |
| Feedback | `list[FeedbackRecord]` + gaps from `get_audit()` where `kb.knowledge_gap` | empty state |
| Evaluation | `get_eval()` keys: `n_test, n_train, ml.*, end_to_end.*, p1.*, security.*, hype.*, wrong_user_category.*, right_user_category.*, review_rate_pct, latency_ms_per_ticket, confusion.*, per_class.*` (+ `search`, `fix`, `fallback` when added) | missing key → "Not measured yet" card |
| MTTR | `MTTRReport.rows[]`, `.overall_reduction_pct`, `.baseline_is_simulated` | `assisted_min is None` → "—" |
| Knowledge base | `list_kb()` → `KBHit[]` + counts from feedback / audit | — |
| Feedback › audit records | `get_audit()` → `AnalysisResult[]`: `analysis_id, analyst, timestamps, decision.outcome, classification.priority/category, decision.confidence` | empty state |
| Sidebar + Settings | `LLMStatus`, `SystemStatus` | — |

### 3.3 Parts not built yet (build the UI anyway)
Today `src/classify.py` exists. `retrieve.py`, `llm.py`, `resolve.py`, `decide.py`, `pipeline.py` and `store.py` may not.
- If `src/pipeline.py` exists, `analyze_ticket` calls it.
- Otherwise `backend.py` builds a **complete `AnalysisResult` that passes `check_result()`**:
  - `cleaned` from `src/text.py`;
  - `classification` from the **real classifier** (with no vote);
  - `similar` / `tiebreak` / `kb` / `fix` = `None`, with their part names added to `missing_parts`;
  - `trace` with `status: "missing"` for those steps.
- Pages render a missing block as a grey card: *"Similar tickets — not available yet (`src/retrieve.py` not built)"*.
- **Interim decision** (same order as the real rules): P1/P2 → ESCALATE · else REVIEW (reason: "fix not available yet"). **Never RECOMMEND without a cited fix**, and `check_result()` enforces this.

**Design fixture (optional):** `app/fixtures/demo_INC-00156.json` holds one full `AnalysisResult`, for building layouts only.
- It must pass `check_result()`.
- It is loaded **only** when the env var `RESOLVEIQ_DESIGN_MODE=1` is set.
- It is shown with a permanent banner: *"DESIGN FIXTURE — not a live result"*.

### 3.4 Storage (if `src/store.py` doesn't exist, create it)
- **SQLite** `data/store/resolveiq.db`:
  - `analyses(analysis_id PK, created_at, recommended_at, resolved_at, analyst, role, ticket_json, result_json, outcome, priority, category, confidence)`
  - `evidence(analysis_id, source_type, source_id, score, excerpt)`
- **Feedback** `data/store/feedback.json`: a list of `{feedback_id, analysis_id, analyst, target_type: "classification|similar_ticket|kb_article|fix", target_id, verdict: "useful|incorrect|unresolved", comment, created_at}`.
- `created_at` = form submit time · `recommended_at` = result ready · `resolved_at` = "Mark resolved" click.

---

## 4. Roles: each role sees only its own pages

Keep this simple. There are 3 roles, each role has its own pages, and **no page is shared**.

| Role | Who | Pages they see | Nothing else |
|---|---|---|---|
| 👤 **Employee** | a normal staff member | 📚 **KB Assistant** | no tickets, no internal articles, no admin pages |
| 🎧 **Support** | help-desk staff | 🎫 **New ticket** · 📁 **Past tickets** | no admin pages, no KB Assistant |
| ⚙️ **Admin** | runs the system | 💬 **Feedback** (incl. audit records) · 📊 **Evaluation** · ⏱️ **MTTR** · 📚 **Knowledge base** · 🔑 **Settings** | no ticket creation |

How to build it:
- **Sidebar:** a "Viewing as" selector (Employee / Support / Admin) and a "Your name" text box, with the caption *"Demo role switch — no real sign-in"*.
- **Pages:** put the page lists in one dict in `app/app.py`, `PAGES_BY_ROLE = {"employee": [...], "support": [...], "admin": [...]}`, and pass only the current role's list to `st.navigation()`. Pages of other roles don't exist in the menu or by URL.
- **Safety check:** each page also starts with `require_role("support")` (in `app/state.py`), which calls `st.stop()` with "This page isn't available for your role" if the role doesn't match.
- **Switching role** clears the previous role's results and chat from `st.session_state`.
- **Content rules that go with the roles:**
  - The KB Assistant always uses **public articles and self-help steps only**.
  - Support sees internal articles and support steps **inside a ticket result** (New ticket › Recommended fix / KB articles).
  - Admin sees every article read-only on the Knowledge base page.

---

## 5. File layout

```
app/
  app.py                  # entry: page config, theme, sidebar (role, name, LLM status), PAGES_BY_ROLE + st.navigation
  backend.py              # the contract in §3
  state.py                # session_state keys + require_role()
  ui.py                   # shared components (badges, banners, chips, cards, feedback widget)
  pages/
    kb_assistant.py       # Employee
    new_ticket.py         # Support
    past_tickets.py       # Support
    feedback.py           # Admin (includes audit records)
    evaluation.py         # Admin
    mttr.py               # Admin
    knowledge_base.py     # Admin
    settings.py           # Admin
  fixtures/demo_INC-00156.json   # optional, design mode only
.streamlit/config.toml           # theme
```

Run with: `streamlit run app/app.py` from the project root. Make imports work from there (`sys.path` insert of the project root in `app.py`).

---

## 6. Visual design

- `st.set_page_config(page_title="ResolveIQ", page_icon="🎫", layout="wide")`.
- `.streamlit/config.toml`: one calm primary colour (e.g. `#2563EB`), light base, a readable sans font. It must also look right in dark mode.
- **Outcome colours:** RECOMMEND green · REVIEW amber · ESCALATE red · NEED INFO blue. **Priority colours:** P1 red · P2 orange · P3 amber · P4 grey.
- **Never rely on colour alone**: every badge also has its text (e.g. "P2", "REVIEW").
- **Confidence:** a percentage + a thin bar. Below 60% is amber, below 40% red.
- Cards use `st.container(border=True)`. Spacing is consistent. Don't overuse emojis: one icon per page title and outcome.
- Every page starts with a **one-line caption** saying what it is for.
- Empty states always explain what to do next (e.g. *"No feedback yet — analyse a ticket on New ticket and rate the result."*).
- The sidebar footer shows: active LLM (Groq / Ollama / none), model file loaded yes/no, search index built yes/no.

---

## 7. Page specifications

### 7.1 🎫 New ticket (the main screen: spend the most effort here)

**Layout:** form on the left (≈ 40%), result on the right (≈ 60%). On narrow screens, the result goes below the form.

**Form fields:**

| Field | Widget | Options / rules |
|---|---|---|
| Description | `text_area`, required | placeholder: "Describe what's wrong, what you tried, and any error message" |
| Service | `selectbox` | `SERVICES` keys |
| Environment | `radio`, horizontal | `ENVIRONMENTS` |
| Who is affected | `radio`, horizontal | `WHO_AFFECTED` |
| Your category guess | `selectbox` | `CATEGORIES` keys |
| Your subcategory guess | `selectbox` | **only** the subcategories of the chosen category |

⚠️ **Streamlit gotcha:** widgets inside `st.form` don't rerun until submit, so a dependent subcategory dropdown can't update inside a form. Put the category and subcategory dropdowns **outside** `st.form` (or don't use a form), and use an "Analyse ticket" button.

**"Try an example" row** (for the demo) fills the form from `data/resolveiq_tickets.jsonl` or fixed text:
1. **INC-00156**: hype + wrong user category + P2
2. **Calm vs hype**: one printer ticket, plus a toggle "Add 'URGENT — I'm the CEO, fix this now!'"
3. **Vague**: "system not working"
4. **Uncovered problem**: "Customers see the wrong prices on the company website" (service Company Website, Production, Customers)

**While analysing:** `st.status("Analysing ticket…", expanded=True)` writes one line per pipeline step as it finishes, e.g. "✓ 3 Classify — 41 ms". Then it collapses.

**Store the result in `st.session_state["result"]`.** Feedback clicks rerun the script, so never re-analyse on rerun.

**Result panel, top to bottom:**

1. **Outcome banner** (full width, coloured):
   - outcome + confidence %;
   - the reasons as bullets;
   - for ESCALATE: "→ hand to **{escalate_to}**";
   - for NEED INFO: the questions, each with a copy button.
2. **Chips row:**
   - "Hype detected — ignored for priority"
   - "You chose {user_category} — model says {category}"
   - "LLM tiebreak used"
   - 🔴 "Possible security issue — check with Security team"
   - "Knowledge gap"
3. **Four label cards:** Category · Subcategory · Symptom type · Priority.
   - Each shows the value, a confidence bar, and an expander "Other candidates" listing `top3`.
   - The Priority card shows the badge, then `priority_reason` in full, then Team, Impact and Urgency in small text.
4. **Tabs:**
   - **Recommended fix:**
     - One block per path: title, "why it fits", then numbered steps.
     - Each step has **citation chips** (`KB-005/support/1`). Clicking a chip opens an expander with the exact source quote.
     - Under the steps: "Verify:" and "Escalate if:" from the article.
     - Footer: "Citation check: 11 of 12 steps verified · 1 step removed (could not be matched to its source)".
     - If `fix` is None: show why (LLM unavailable / knowledge gap / not built).
   - **Similar past tickets:**
     - A table: ID, excerpt, category › subcategory, priority, match %, why matched, "Possible duplicate" badge.
     - Above it: "Vote: 4 of 5 similar tickets are {category}".
   - **KB articles:** top 3 with title, access level, match %, why matched, and an expander showing the full article (role-filtered).
   - **Trace:**
     - The 9 steps + 5b as a table: step, what ran, time in ms, key output.
     - Then thresholds used (0.75 acceptance, 0.20 security), the LLM used, and `missing_parts`.
     - This is where a judge checks traceability.
   - **Audit record:** the full JSON (PII masked) + download button.
5. **Feedback** (FR-06):
   - Under each label card, each similar ticket, each KB article and the fix: a 3-way control **Useful / Incorrect / Unresolved** (`st.segmented_control`) + optional comment + Save.
   - After saving, show a small "Saved ✓" toast (`st.toast`). The control stays editable.
6. **"Mark resolved"** button (sets `resolved_at`, feeds MTTR). Show "Resolved at 14:32 · time to resolve 6 min".

### 7.2 📁 Past tickets (FR-07)

- **Filters** in a top row of `multiselect`s: service, category, subcategory (narrowed by the chosen categories), priority, team, environment, who affected, plus a text search box.
- **Caption:** "Date and status filters aren't available: the dataset has no date or status fields."
- **Table:** `st.dataframe` with `column_config`: priority as a coloured text column, description truncated, a row count above it.
  - Use `on_select="rerun", selection_mode="single-row"`. Selecting a row opens its details below: all fields, plus a "Generated labels" note.
- **Export filtered CSV** button (PII masked).

### 7.3 📚 KB Assistant (Employee)

- Chat UI (`st.chat_message`, `st.chat_input`). Chat history lives in session state, with a "New chat" button.
- Each answer shows:
  - the steps, as numbered text with citation chips;
  - a "Sources" expander listing the article titles and match %.
- Answers come **only** from public articles, and only from their self-help steps (`ask_kb(question, role="employee")`).
- **No good match:** *"I couldn't find this in the knowledge base. Please raise a ticket with the Service Desk."* plus a button that copies a ready-to-paste summary.
- Three example questions as buttons, e.g. "I forgot my password", "VPN connects but shared drives won't open", "How do I share my calendar?".

### 7.4 💬 Feedback (Admin)

- **KPI tiles:** total feedback · % useful · % incorrect · open knowledge gaps.
- **Tables:**
  - per support person (useful / incorrect / unresolved counts);
  - per KB article (same counts, sorted by most "incorrect");
  - knowledge gaps (analysis id, description excerpt, predicted subcategory, date).
- Filter by person. Export CSV.
- **Audit records (FR-08)**, a section at the bottom of this page (not a separate page):
  - Table of analyses: time, support person, outcome, priority, category, confidence, resolved yes/no. Filter by outcome and priority.
  - Row select → the full record (input, predictions, evidence, fix, decision, feedback, timestamps).
  - **Export CSV / JSON** (PII masked).

### 7.5 📊 Evaluation (reads `reports/eval_results.json`)

- **Header:** "Held-out test set: {n_test} tickets, trained on {n_train}. Labels are generated."
- **KPI tiles with comparison:**
  - category accuracy vs "trust the user" vs "most common";
  - same for subcategory;
  - symptom accuracy;
  - priority accuracy;
  - P1s caught / missed (+ "missed but flagged");
  - wrong user category corrected;
  - REVIEW rate;
  - ms per ticket.
- **Confusion matrices** (category, symptom type, priority): show `reports/confusion_*.png` side by side, or re-draw from `confusion` as an Altair heatmap.
- **Hype resistance** card and **Security safety net** card (caught, flagged, false alarms).
- **Search quality** section (keyword vs vector vs hybrid: Recall@5, MRR), **Fix quality** (citation validity) and **Fallback** (% of probe tickets sent to a human): read from the same JSON if present, otherwise a "Not measured yet" card.
- **"Re-run evaluation"** button: runs `python -m build.run_eval` via `subprocess` with a spinner, then reloads. Warn that it takes a while.
- Link to `reports/EVALUATION.md`.

### 7.6 ⏱️ MTTR (FR-09)

- **Baseline:** simulated manual handling minutes per priority, in one constant in `app/backend.py`, e.g. `{"P1": 240, "P2": 480, "P3": 1440, "P4": 2880}`. Label it **"Simulated baseline"** everywhere, and state the assumption in an info box.
- **Assisted:** from SQLite, `resolved_at − created_at` for resolved analyses. Also show "time to recommendation" (`recommended_at − created_at`).
- **Bar chart:** baseline vs assisted per priority. Show **n** (number of resolved tickets) on each bar, because small samples must be visible.
- **KPI:** overall % reduction. Show "—" until at least 1 ticket is resolved.

### 7.7 📚 Knowledge base (Admin)

- Search box + filters (category, subcategory, access level, service).
- List: kb_id, title, access badge, times cited (from audit), useful / incorrect counts.
- Detail view: symptoms, error messages, cause, self-help steps, support steps (with step IDs as shown to the LLM, e.g. `KB-005/support/2`), verify, escalate when, related articles (clickable).
- Caption: "Read-only. Articles are generated by us (`Prompts/KB_GENERATION_PROMPT.md`)."

### 7.8 🔑 Settings (Admin)

- Groq API key (`type="password"`) + "Test connection" → ✅ / ❌ with a plain message. After saving, show the masked key.
- Checkbox "Remember on this machine (writes to .env)".
- Model choice: `llama-3.3-70b-versatile` (default) / `llama-3.1-8b-instant`.
- Ollama status (ping `http://localhost:11434`) + model name `qwen2.5:7b`.
- **Active LLM** line: "Groq" / "Ollama (Groq unavailable)" / "None: fixes can't be written; tickets will be escalated".
- **System status** table from `system_status()`: model file, search index, each `src/` module built or missing, with the command to build it (e.g. `python -m build.train_models`).

---

## 8. Performance and robustness

- Load once with `@st.cache_resource`: the classifier (`TicketClassifier.load()`), the embedding model, ChromaDB, BM25.
- Load with `@st.cache_data`: the ticket JSONL, the KB JSON, the eval JSON.
- Classification + rules take ~130 ms today. The page must feel instant apart from LLM calls, which always run inside `st.status` / `st.spinner`.
- **Missing model file:**

  > "Model not trained yet. Run: `python -m build.train_models`"

  Shown as `st.error` with a code block, and the app does **not** crash.
- **Missing search index:** same pattern with `python -m build.build_index`.
- **LLM errors** become a friendly banner. **Never** show a raw traceback in the UI. Log it to the console without the API key.
- Every page must work with empty storage (first run).

---

## 9. Acceptance checklist (test all of these before saying "done")

**Demo script** (from `Docs/PROJECT_OVERVIEW.md` §14):
- [ ] INC-00156 example:
  - hype chip shown;
  - "You chose Device & Software — model says Account & Access" chip;
  - priority **P2** with its reason;
  - outcome ESCALATE → Service Desk (or REVIEW with reasons, if parts are missing).
- [ ] Calm vs hype toggle: **same priority** both times, hype chip only on the hype version.
- [ ] "system not working": NEED INFO with questions (or REVIEW while `decide.py` is missing, with the reason shown).
- [ ] Wrong website prices: knowledge gap → ESCALATE (once retrieval exists), and logged as a gap.
- [ ] Evaluation page shows the real numbers from `reports/eval_results.json` (e.g. category 96.1% vs 80.6% trust-the-user).
- [ ] Feedback saved → appears on the Feedback page. Mark resolved → appears on the MTTR page.

**Safety:**
- [ ] As **Employee**: the menu shows only KB Assistant. Answers never contain an internal article or a support step.
- [ ] As **Support**: the menu shows only New ticket and Past tickets.
- [ ] As **Admin**: the menu shows only Feedback, Evaluation, MTTR, Knowledge base and Settings.
- [ ] Opening another role's page by URL shows "This page isn't available for your role".
- [ ] Switching role clears the previous role's results and chat.
- [ ] The API key never appears in the UI after saving, in logs, in the audit export or in `result_json`.
- [ ] Exports contain no email address or phone number (test with a ticket that has both).
- [ ] No button anywhere closes a ticket or changes a system.

**Quality:**
- [ ] No page throws on an empty database or a missing optional module.
- [ ] Every number on screen can be traced to a source (result JSON, eval JSON or SQLite).
- [ ] Simulated / generated labels are visible on the MTTR, Evaluation and Past tickets pages.
- [ ] Usable at 1280 px wide and readable when projected (base font ≥ 14 px).

---

## 10. Out of scope (don't build)

Real authentication, multi-user concurrency, editing KB articles, editing tickets, ticket closing or ITSM write-back, email notifications, the add-ons in `Docs/PROJECT_OVERVIEW.md` §15 (storm alerts, two-problem tickets, feedback boost, queue page) unless I ask.

---

## 11. How to work

1. Read the files in §0. Then write a short plan: the files you'll create, and the order.
2. Build in this order:
   1. `backend.py` + `state.py` + `ui.py`
   2. **New ticket** (the real classifier first)
   3. Past tickets
   4. Evaluation
   5. Settings
   6. KB Assistant
   7. Feedback (with audit records)
   8. MTTR
   9. Knowledge base
3. After each page, run `streamlit run app/app.py` and check it in the browser.
4. Keep functions small with docstrings that say *why*, not *what*. Add type hints.
5. When finished, report:
   - what works;
   - what shows "not available yet" and which module would enable it;
   - the acceptance checklist with ✅ / ❌ for each item;
   - any place you had to deviate from this prompt, and why.
