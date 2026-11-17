# Problem Statement — Intelligent IT Ticket Analysis and Resolution Assistant

> Source: `ticket.pdf` (HCLTech | Future Ready AI Engineer Hackathon — "Mail 2a - Use Cases - AI Engg.", *Problem Statement and Participant Brief*).
> Part A below is a faithful extraction of the brief. Part B is **our own interpretation** (checklists, implied requirements) — not from the brief.

---

## PART A — Extracted from the brief

| Field    | Value                                                  |
|----------|--------------------------------------------------------|
| Use case | Intelligent IT Ticket Analysis and Resolution Assistant |
| Industry | Enterprise IT / Service Management                     |

### 1. Problem Statement

Enterprise IT support systems receive large volumes of tickets involving **access issues, application failures, configuration problems and recurring incidents**. Manual classification, duplicate detection and resolution lookup increase handling time and can lead to inconsistent outcomes, directly driving up **Mean Time to Resolve (MTTR)**, a critical service management measure.

**Goal:** Build an assistant that **analyzes incoming tickets**, **identifies similar historical cases** and **recommends an evidence-backed resolution** that a support analyst can **review and act on**, with the goal of **measurably reducing MTTR**.

### 2. Functional Requirements

| ID    | Capability                         | Requirement |
|-------|------------------------------------|-------------|
| FR-01 | Ticket classification              | Assign a category, subcategory, priority or intent using a defined taxonomy, and expose a confidence score. |
| FR-02 | Duplicate and similarity detection | Retrieve and rank similar historical tickets using title, description, symptoms, affected service and available metadata. |
| FR-03 | Resolution recommendation          | Recommend one or more likely resolution paths based on resolved historical cases or approved knowledge. |
| FR-04 | Evidence and traceability          | Show the source ticket or knowledge reference, relevant excerpt and reason each item supports the recommendation. |
| FR-05 | Confidence and fallback            | Flag low-confidence results, avoid unsupported conclusions and provide a clear human-review or escalation path. |
| FR-06 | Analyst feedback                   | Allow the reviewer to mark a match or recommendation as useful, incorrect or unresolved. |
| FR-07 | Search and filtering               | Support filters such as application, category, date, status, assignment group or environment where the seed data permits. |
| FR-08 | Audit-friendly output              | Capture the input, predicted classification, retrieved evidence, recommendation and reviewer decision for evaluation. |
| FR-09 | MTTR measurement                   | Capture ticket creation, recommendation and resolution timestamps to calculate MTTR, and report MTTR with the assistant against a manual-handling baseline. |

### 3. Expected Submission

1. **Working prototype** — A usable ticket-analysis interface **or** API that demonstrates the end-to-end flow on the supplied or candidate-created sample data.
2. **Evaluation report** — A concise report describing the **dataset, evaluation method, results, observed errors and known limitations**.
3. **Evidence-backed examples** — **At least three** worked examples showing the **input ticket, classification, similar cases, recommended resolution and source evidence**.
4. **Technical documentation** — A **README** with **setup and run instructions, architecture summary, key assumptions and design trade-offs**.

### 4. Evaluation Guidance (how judges score)

| Dimension                    | What good looks like |
|------------------------------|----------------------|
| Classification quality       | Evaluate category, subcategory and priority predictions against labelled tickets, including **confusion between operationally important classes**. |
| Duplicate retrieval quality  | Measure whether genuinely related historical tickets appear **near the top** of the ranked results and **distinguish them from superficial keyword matches**. |
| Resolution usefulness        | Use analyst review to assess whether the recommended resolution is **relevant, actionable and supported by source evidence**. |
| Confidence and fallback      | Verify that **weak or contradictory evidence** results in a **low-confidence response, clarification request or human escalation**. |
| Traceability                 | Confirm that classifications, duplicate candidates and recommendations can be **traced to ticket fields or approved knowledge sources**. |

### 5. Scope Boundaries

- The solution should **analyze and recommend**. **Out of minimum scope:** automatic closure, privileged remediation, production ITSM changes.
- May use **rules, ML, semantic retrieval or GenAI** — provided the result is **explainable and evidence-backed**.
- **Synthetic or de-identified** ticket data may be used; any **generated labels or assumptions must be clearly identified**.
- **Sensitive ticket content and access restrictions must be respected** in retrieval, display and exported results.

---

## PART B — Our working interpretation (not in the brief)

### B1. Requirement → "done when" checklist

| ID    | Done when… | Evaluation dimension it feeds |
|-------|------------|-------------------------------|
| FR-01 | Every analyzed ticket shows category + subcategory + priority (and/or intent) from a **written-down taxonomy**, each with a numeric confidence. | Classification quality |
| FR-02 | Top-k similar historical tickets are listed with a similarity score; ranking uses more than raw keywords (semantic + metadata such as service). | Duplicate retrieval quality |
| FR-03 | 1+ resolution paths are proposed, each derived from resolved tickets or KB articles (not invented). | Resolution usefulness |
| FR-04 | Each recommendation shows: source ID (ticket/KB), the excerpt used, and a one-line "why this supports it". | Traceability |
| FR-05 | Below a threshold (or when sources conflict), UI shows a low-confidence flag and an escalate / ask-for-clarification path instead of a confident answer. | Confidence and fallback |
| FR-06 | Analyst can click **Useful / Incorrect / Unresolved** on matches and recommendations; the choice is stored. | Resolution usefulness |
| FR-07 | Filters exist for fields the dataset actually has (application, category, date, status, assignment group, environment). | Duplicate retrieval quality (narrows search) |
| FR-08 | One audit record per analysis: input, predicted classes, evidence retrieved, recommendation, reviewer decision — exportable (e.g., CSV/JSON). | Traceability |
| FR-09 | Timestamps stored for created / recommended / resolved; a view compares MTTR **with assistant vs manual baseline**. | Business impact (core goal) |

### B2. Deliverables checklist

- [ ] Prototype (UI or API) running end-to-end on sample data
- [ ] Sample dataset (synthetic/de-identified) + taxonomy; generated labels clearly marked
- [ ] Evaluation report: dataset · method · results (classification metrics + confusion matrix, retrieval metrics) · observed errors · limitations
- [ ] ≥ 3 worked examples (input → classification → similar cases → resolution → evidence)
- [ ] README: setup/run · architecture · assumptions · trade-offs

### B3. Implied requirements / easy-to-miss points

- **Confusion between important classes** — judges want a confusion matrix, not just accuracy (e.g., P1 vs P2 mistakes matter more).
- **"Superficial keyword matches"** — a pure keyword search will be marked down; show that semantic/metadata ranking beats it (e.g., a baseline comparison).
- **Contradictory evidence** — not only "low score" but "top results disagree" should trigger fallback.
- **Access restrictions** — some notion of sensitive/restricted tickets that are masked or hidden per user role, including in exports.
- **MTTR baseline** — needs a defined manual-handling baseline (e.g., historical resolution times in the seed data), with the assumption stated.
- **Human-in-the-loop only** — the assistant recommends; it never closes tickets or changes systems.
