# ResolveIQ Dashboard (Streamlit) — what is being built

> **Status: BUILT (v1).** All 8 pages render for their role and block the other roles (Streamlit AppTest).
> This README began as the plan for other agents; it now records what exists, which files the dashboard owns,
> and what it expects from the rest of the repo. Keep building against `src/contracts.py`.
>
> Full spec: [`Prompts/DASHBOARD_PROMPT.md`](../Prompts/DASHBOARD_PROMPT.md). If this file and the spec disagree, the
> spec + `Docs/` win; the deviations listed in §7 are deliberate and match today's code.

---

## 1. One-line summary

A role-based Streamlit app on top of `src/pipeline.py`:
- **Employees** ask the KB.
- **Support** analyses tickets and gets a cited fix plus evidence.
- **Admins** see feedback, audit records, evaluation, MTTR and settings.

It **analyses and recommends only**. There is no button that closes a ticket or changes a system.

```bash
streamlit run app/app.py
```

---

## 2. Status board

| # | Piece | File(s) | Status |
|---|---|---|---|
| 1 | Backend facade (the only thing pages call) | `app/backend.py` | ✅ done |
| 2 | Session state + role guard | `app/state.py` | ✅ done |
| 3 | Shared UI parts (outcome banner, chips, confidence bar, priority badge, feedback widget) | `app/ui.py` | ✅ done |
| 4 | Entry point, sidebar, role → pages | `app/app.py`, `.streamlit/config.toml` | ✅ done |
| 5 | 🎫 New ticket (main demo screen) | `app/pages/new_ticket.py` | ✅ done |
| 6 | 📁 Past tickets | `app/pages/past_tickets.py` | ✅ done |
| 7 | 📊 Evaluation | `app/pages/evaluation.py` | ✅ done |
| 8 | 🔑 Settings | `app/pages/settings.py` | ✅ done |
| 9 | 📚 KB Assistant | `app/pages/kb_assistant.py` | ✅ done |
| 10 | Audit + feedback storage (SQLite + JSON) | `src/store.py` | ✅ done (dashboard owns it, see §5) |
| 11 | 💬 Feedback + audit records | `app/pages/feedback.py` | ✅ done |
| 12 | ⏱️ MTTR | `app/pages/mttr.py` | ✅ done |
| 13 | 📚 Knowledge base viewer | `app/pages/knowledge_base.py` | ✅ done |

Verified: every page renders without exceptions for its role and blocks other roles; INC-00347 (+ hype) gives P2 + hype chip +
"you chose X" chip; one real Ollama run gave RECOMMEND with 100% citation validity (≈ 5 min on CPU — use a Groq key for demos).

---

## 3. Pages by role (each role sees only its own pages)

The sidebar has a **"Viewing as"** selector (Employee / Support / Admin) and a **"Your name"** box. The caption says
*"Demo role switch — no real sign-in"*. Pages of other roles aren't in the menu, and each page also calls
`require_role(...)`. Switching role clears the previous role's results and chat.
How roles work end to end (dropdown → menu → page guard → role-filtered search): [`Docs/ROLE_BASED_ACCESS.md`](../Docs/ROLE_BASED_ACCESS.md).

| Role | Pages | What a judge sees |
|---|---|---|
| 👤 Employee | 📚 **KB Assistant** | Chat answers built only from public articles and self-help steps, with citation chips and a Sources expander. When nothing matches: "raise a ticket". |
| 🎧 Support | 🎫 **New ticket** · 📁 **Past tickets** | See §3.1. Past tickets has filters (service, category, subcategory, priority, team, environment, who affected, text search), row details and a masked CSV export. |
| ⚙️ Admin | 💬 **Feedback** · 📊 **Evaluation** · ⏱️ **MTTR** · 📚 **Knowledge base** · 🔑 **Settings** | Feedback KPIs, results per analyst and per article, knowledge gaps, audit records with CSV/JSON export · metrics + confusion matrices + keyword-vs-vector-vs-hybrid search table · simulated baseline vs assisted MTTR · read-only article browser · Groq key (masked), Ollama status, system status. |

### 3.1 New ticket: the main screen

- **Left side:** the ticket form.
  - Every option list comes from `src/taxonomy.py`.
  - The subcategory list only shows the chosen category's subcategories.
  - **Test cases** buttons fill the form with the 6 demo tickets from [`Docs/DEMO_SCRIPT.md`](../Docs/DEMO_SCRIPT.md), in script order: VPN outage (P1), VPN + shared drive (RECOMMEND, also used for the hype toggle), INC-00347 + hype (held-out), wrong website prices (knowledge gap), vague, and ransomware (Security P1). Hover over a button to see its expected result. The KB Assistant has its own 4 test-case questions.
- **Right side**, top to bottom:
  1. **Outcome banner:** RECOMMEND green, REVIEW amber, ESCALATE red, NEED INFO blue. Shows the confidence, the reasons, who to escalate to, and the clarifying questions.
  2. **Chips:** hype ignored · "you chose X, model says Y" · possible security issue · knowledge gap · tiebreak used.
  3. **Four label cards:** Category, Subcategory, Symptom type and Priority. Each has a confidence bar and its top-3 alternatives. Priority also shows its reason, team, impact and urgency.
  4. **Tabs:**
     - **Recommended fix:** numbered steps with citation chips that open the source quote, plus the citation-check footer.
     - **Similar past tickets:** the vote, match %, why each matched, and a possible-duplicate badge.
     - **KB articles.**
     - **Trace:** each step, its time in ms, and contract warnings.
     - **Audit record:** the masked JSON, with a download button.
  5. **Feedback:** Useful / Incorrect / Unresolved on every label, similar ticket, article and fix.
  6. **Mark resolved:** feeds MTTR.

---

## 4. Integration contract: what the dashboard calls

Pages call **only** `app/backend.py`. The backend calls `src/*`. All data shapes come from `src/contracts.py`, and the
dashboard never redefines them.

| Backend function | Calls into | Returns |
|---|---|---|
| `analyze_ticket(ticket, role, analyst)` | `src.pipeline.analyze_ticket` → then `src.store.save_analysis` | `AnalysisResult` |
| `ask_kb(question, role="employee")` | `src.pipeline.ask_kb` | `KBAnswer` |
| `list_tickets(filters, role)` / `get_ticket(id, role)` | `data/resolveiq_tickets.jsonl` (+ `mask_pii`) | `DataFrame` / `dict` |
| `list_kb(filters, role)` | `src.kb.load_articles` + `access_for(role)` | `list[KBHit]` |
| `add_feedback(rec)` / `get_feedback(analyst)` | `src.store` | `FeedbackRecord` |
| `mark_resolved(analysis_id)` | `src.store` | sets `timestamps.resolved_at` |
| `get_audit(filters)` / `export_audit(filters, fmt)` | `src.store` | `AnalysisResult[]` / masked `bytes` |
| `get_mttr()` | `src.store` + simulated baseline constant | `MTTRReport` |
| `get_eval()` | `reports/eval_results.json` **and** `reports/rag_eval_results.json` | `dict` |
| `llm_status()` / `set_api_key(key, remember)` | env vars read by `src/llm.py` | `LLMStatus` |
| `system_status()` | checks model file, `data/store/chroma`, `src/*.py` | `SystemStatus` |

**Loading:** heavy objects load once with `st.cache_resource`. `src/pipeline.py` already caches the classifier and
retriever with `lru_cache`. Files load with `st.cache_data`.

---

## 5. What other agents can expect, and what I need from you

**Files the dashboard owns.** Please don't edit these; message me instead:
`app/**`, `.streamlit/config.toml`, `src/store.py` (new), `data/store/resolveiq.db`, `data/store/feedback.json`.
In `requirements.txt` I will only add `streamlit>=1.40`.

**Files I will NOT touch:** `src/pipeline.py`, `classify.py`, `retrieve.py`, `resolve.py`, `decide.py`, `llm.py`,
`text.py`, `kb.py`, `rules.py`, `taxonomy.py`, `build/*`, `reports/*`.
- If I need a new field, I'll ask for it here and bump `CONTRACT_VERSION`. I won't patch it myself.

**What I rely on (please keep it stable):**
1. `src.pipeline.analyze_ticket(ticket, role, analyst, use_llm)` returns a dict that passes `check_result()`.
   - The dashboard shows contract warnings on the Trace tab; it doesn't crash on them.
2. `src.pipeline.ask_kb(question, role)` returns a `KBAnswer`.
3. Any field that may be `None` (`similar`, `tiebreak`, `kb`, `fix`) stays `None` when unavailable.
   - Every one of these has a grey "not available yet" card, so empty is safe. Fake values are not.
4. `missing_parts` lists the parts that aren't built yet.
   - When `src/store.py` lands, I'll remove `"store"` from it **inside the backend**, so the pipeline doesn't need to change.
5. Eval JSON keys stay as they are today.
   - `eval_results.json`: `n_test, n_train, ml, end_to_end, p1, security, hype, wrong_user_category, right_user_category, review_rate_pct, latency_ms_per_ticket, confusion, per_class`
   - `rag_eval_results.json`: `tickets/kb/kb_with_hint × keyword/vector/hybrid, n_test, llm`
   - New keys are fine. A key that's missing shows "Not measured yet".
6. The LLM is configured by env vars, as `src/llm.py` documents: `GROQ_API_KEY`, `GROQ_MODEL`, `OLLAMA_MODEL`, `OLLAMA_URL`.
   - The Settings page sets these in the running process. It writes `.env` only when the admin ticks "remember".

**What you get from the dashboard:**
- **A stored record for every analysis** (FR-08), using the shared timestamps (`created_at`, `recommended_at`, `resolved_at`) as specified.
  - SQLite schema: `analyses(analysis_id PK, created_at, recommended_at, resolved_at, analyst, role, ticket_json, result_json, outcome, priority, category, confidence)` and `evidence(analysis_id, source_type, source_id, score, excerpt)`.
- **Feedback records** (`FeedbackRecord`) in `data/store/feedback.json`. You can read these for evaluation or a feedback boost.
- **A UI** that shows the effect of any pipeline change as soon as you rerun Streamlit.

---

## 6. Ground rules the UI follows

- **No business logic in pages.** No classification, priority, search or LLM code lives in the UI.
- **Personal data is hidden everywhere.** Emails, phone numbers and employee IDs are masked with `src.text.mask_pii` on screen and in exports.
- **API key safety.**
  - The key goes in a password field and is shown only as `gsk_••••abcd`.
  - It is never logged, never shown in an error and never written to the audit log.
- **Honest labels.** The MTTR baseline is marked *"Simulated baseline"*. Dataset labels are marked *"Generated labels"*.
- **Never a fake result.** Unbuilt parts show "Not available yet — `<file>` not built".
- **Design fixture only on request.** `app/fixtures/demo_INC-00156.json` loads only when `RESOLVEIQ_DESIGN_MODE=1`, and the page then carries a permanent banner.
- **Friendly failures.** Raw tracebacks never reach the UI. A missing model or index shows the command to build it:
  `python -m build.train_models`, `python -m build.build_index`.

---

## 7. Known gaps and deviations (matching today's code)

| Item | Today | What the dashboard does |
|---|---|---|
| LLM tiebreak (step 5b) | `tiebreak` is always `None` | Hides the chip; the Trace tab shows "not needed / not built" |
| `Fix` extra keys | `resolve.py` adds `llm_model` and `dropped_reasons` | Shows `llm_model` in the fix footer and `dropped_reasons` in the Trace tab; both are optional |
| Ollama default model | `qwen2.5:3b` (`src/llm.py`), not 7b as the spec says | Settings shows whatever `OLLAMA_MODEL` is set to |
| Search metrics | a separate file, `reports/rag_eval_results.json` | The Evaluation page reads both JSON files |
| Audit store | `src/store.py` doesn't exist yet | The dashboard builds it (§5) |
| Date / status filters (FR-07) | not in the dataset | Past tickets shows a caption explaining why |
| Live progress per step | the pipeline returns `trace` only at the end | `st.status` replays the trace lines after the call. The LLM step runs under a spinner |
| KB Assistant: no match vs no LLM | `KBAnswer` has no `reason` field; both give `answered=False` | Page checks `llm_status()` and says "no language model available" instead of "not in the KB". **Ask:** add `reason` to `KBAnswer` |
| MTTR demo data | `build/seed_mttr_demo.py` (not dashboard-owned) can add 60 fake resolved records | They are marked analyst "Simulated demo data", ids `DEMO-…`; remove with `python -m build.seed_mttr_demo --clear` |
| Speed with local LLM | `qwen2.5:3b` on CPU takes minutes per fix | Set a Groq key on Settings for live demos, or untick "Write a cited fix" for a fast run |

---

## 8. Done when (acceptance, short form)

**Demo cases:**
- [ ] **INC-00347 + hype:** the hype chip and the "chose Device & Software, model says Business System" chip show, priority is **P2** with its reason, and the outcome is ESCALATE → Applications.
- [ ] **Calm vs hype:** same priority both times; the hype chip appears only on the hype version.
- [ ] **"System not working":** NEED INFO with questions.
- [ ] **Wrong website prices:** knowledge gap → ESCALATE, and it's listed on the Feedback page.

**Data shown is real:**
- [ ] The Evaluation page shows the real numbers.
- [ ] Saved feedback shows up on the Feedback page.
- [ ] A ticket marked resolved shows up on the MTTR page.

**Safety:**
- [ ] Each role's menu shows only its own pages, and opening another role's page by URL is blocked.
- [ ] The Employee chat never shows internal articles or support steps.
- [ ] No email address or phone number appears in any export.
- [ ] The API key never appears on screen, in logs or in an export.

**Robustness:**
- [ ] Every page works with an empty database and with optional modules missing.
- [ ] The app is readable at 1280 px wide.
