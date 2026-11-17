# ResolveIQ: Live Demo Script

About **10 minutes**. Every input below was run through the real pipeline on 2026-11-17 and gave the result shown.
LLM wording can change a little between runs. The outcomes, priorities, labels and cited articles did not.

**Nothing to type:** every input is a **Test cases** button in the app (KB Assistant for Employee, New ticket for
Support), in the same order as this script. Hover over a button to see its expected result.

**The story:** an employee tries self-help → it can't help → they raise a ticket → Support analyses it with
ResolveIQ → Admin sees how well it's working.

| # | Feature | Role in sidebar | Time |
|---|---|---|---|
| 1 | **KB Assistant**: self-help answers from public articles, with citations | 👤 Employee | 1.5 min |
| 2 | **Ticket analysis**: classify, prioritise, find similar tickets, cited fix, decision | 🎧 Support | 5 min |
| 3 | **Admin**: feedback + audit, evaluation, MTTR, knowledge base, settings | ⚙️ Admin | 2.5 min |

---

## 0. Before the judges arrive (5 min)

1. Start the app from the project root:
   ```bash
   streamlit run app/app.py
   ```
2. Check the sidebar: **🟢 LLM: Groq**, **🟢 Model file loaded**, **🟢 Search index built**.
3. Type your name in **Your name** (sidebar). Your feedback and audit records are saved under it, and you'll filter by
   it in Feature 3.
4. **Warm up:** switch to Support, click **VPN on, shared drive off**, then **Analyse ticket**. The first run loads the
   models (~15–30 s). After that each ticket takes ~2–3 s.
5. Keep [`reports/EXAMPLES.md`](../reports/EXAMPLES.md) open in another tab as a backup.

> Groq key #1 hit its rate limit (HTTP 429) during testing today. The app switched to the spare key by itself.
> If every route fails, use the backup plan in §5.

---

## Opening line (30 s)

> "IT support teams lose time classifying tickets, hunting for duplicates and looking up fixes. ResolveIQ reads a
> new ticket, classifies it, finds similar past tickets and drafts a fix where **every step cites an approved
> knowledge-base article**. It only analyses and recommends. A human always makes the final call."

---

## Feature 1: KB Assistant (👤 Employee)

Set **Viewing as → Employee**. The only page is **KB Assistant**.

### 1a. A question it can answer
**Click:** `I forgot my password`

**You'll see:** 3 numbered steps, each with a badge `KB-001/self/1`, `/2`, `/3`. Click **Source** next to a step →
the exact sentence from the article. **Sources** expander → *KB-001 I forgot my Company Login password* (64% match).

**Say:** "The answer is written *only* from public articles. Every step is checked by code against the sentence it
cites, so the model can't invent a step."

### 1b. A question it must NOT answer
**Click:** `Nobody in the office can connect to the VPN`

**You'll see:** *"I couldn't find this in the knowledge base. Please raise a ticket with the Service Desk."* plus a
ready-to-paste ticket summary with a copy button.

**Say:** "There *is* an article for this, KB-022. It's **internal**: it holds support-team steps such as checking the
VPN gateway. Employees never see internal articles. The filter runs *before* the search, so the LLM never sees them
either. So the employee raises a ticket…" → switch to Support.

---

## Feature 2: Ticket analysis (🎧 Support)

Set **Viewing as → Support**. Page **New ticket**: the form is on the left, the result on the right.

**Point out the layout once, on the first result:** the outcome banner (colour + reasons) → chips → 4 label cards
with confidence bars (Category, Subcategory, Symptom type, Priority with its reason) → tabs: **Recommended fix ·
Similar past tickets · KB articles · Trace · Audit record**.

### 2a. The employee's ticket: P1 + access control → ⬆️ ESCALATE
**Click:** `VPN outage · P1` → **Analyse ticket**
*(Nobody in the office can connect to the VPN · VPN · Production · Many teams · guess Network › VPN problem)*

**You'll see:** ⬆️ **ESCALATE → Network**, **P1**: *impact High (many teams, critical service) × urgency High (outage,
production)*. Category Network › VPN problem, symptom **outage**.
**Recommended fix** tab: 4 support steps from **KB-022 *VPN won't connect for anyone***. **KB articles** tab: KB-022
has an orange **internal** badge.

**Say:** "Same problem the employee asked about. Support can see the internal article, the employee couldn't. P1
always goes to a human engineer, and the cited fix is attached to save them time."

### 2b. Happy path → ✅ RECOMMEND
**Click:** `VPN on, shared drive off` → **Analyse ticket**
*(My VPN says connected but the shared drive will not open from home. · VPN · Not applicable · Just me)*

**You'll see:** ✅ **RECOMMEND · confidence 94%**: *"classifier, similar tickets and KB agree"*.
Network 99% · VPN problem 96% · **P3** · team Network.

Walk through the tabs. **This is the main "traceability" moment:**
- **Recommended fix**: 7 steps from **KB-020 *VPN connects but shared drives don't open***. Click a citation chip
  (e.g. `KB-020/self/1`) → the exact source text. Footer: *"Citation check: 7 of 7 steps verified · written by
  groq:openai/gpt-oss-120b"*.
- **Similar past tickets**: *"Vote: 5 of 5 similar tickets are Network"*, each with its match % and why it matched.
- **KB articles**: KB-020 (public) at 82%, far ahead of the next one (53%).
- **Trace**: every pipeline step with its time in ms and its key output.
- **Audit record**: the full JSON (personal data masked), with a download button.

**Then:**
- Click **Useful** under the fix → **Save** (toast: *Saved ✓*). This is analyst feedback (FR-06).
- Click **Mark resolved** at the bottom. This feeds MTTR (FR-09).

### 2c. Hype test: shouting doesn't change anything
Keep the VPN ticket. Switch on **Add "URGENT — I'm the CEO" (hype test)** → **Analyse ticket**.

**You'll see:** the **same** result: RECOMMEND, P3, 94%, the same 7 cited steps. The only difference is a purple
chip: **"Hype detected — ignored for priority"**.

**Say:** "Priority comes from **facts**: which service, which environment, who is affected, and the symptom. Never
from tone. We tested this on 168 tickets: the priority never changed."

### 2d. Wrong guess + hype on a real held-out ticket → ⬆️ ESCALATE (P2)
**Click:** `INC-00347 · wrong guess` → **Analyse ticket**
*(This ticket was held out: never used for training, not in the search index.)*

**You'll see:** ⬆️ **ESCALATE → Applications**, **P2**: *impact Medium (just me, critical service) × urgency High
(blocked, production)*. Two chips:
- **Hype detected — ignored for priority**
- **You chose Device & Software — model says Business System**

Business System 97% · Error or won't open 97%. Similar tickets: 5 of 5 vote Business System (all payroll). Fix: 4 support steps
from **KB-030** (internal).

**Say:** "The user picked the wrong category. The model corrected it, and 5 similar past tickets independently agree.
We still show the disagreement instead of silently overriding the user. P2 → a human owns it."

### 2e. No article for this problem → ⬆️ ESCALATE (knowledge gap)
**Click:** `Uncovered problem` → **Analyse ticket**
*(Customers see the wrong prices on the company website since this morning. · Company Website · Production · Customers)*

**You'll see:** ⬆️ **ESCALATE → Applications**, P2, chip **Knowledge gap**. The Recommended fix tab says
*"knowledge gap: no approved KB article fits this ticket"*. The KB articles tab shows a warning; the closest article
is **KB-035, a Finance dashboard article**.

**Say:** "A naive RAG system would answer from that Finance article because it *sounds* similar. We left this gap in
the knowledge base on purpose. ResolveIQ doesn't invent a fix. It escalates and logs the gap for the KB team."

### 2f. Too vague → ❓ NEED INFO
**Click:** `Vague ticket` → **Analyse ticket** *(system not working)*

**You'll see:** ❓ **NEED INFO · confidence 40%**, with two questions to send back (each with a copy button):
*Which application, device or service is affected?* · *What exactly happens, and is there an error message?*

**Say:** "The classifier still gives a confident-looking 94% for Device & Software, because 'not working' is common
in computer tickets. That's why we check vagueness on the *text* before trusting any score."

### 2g. (If time) Hidden security issue → ⬆️ ESCALATE (P1, Security)
**Click:** `Ransomware · security` → **Analyse ticket**
*(My laptop got very slow after I opened an invoice attachment, and now a window says my files are encrypted and asks
for payment. · Laptop / Desktop · Production · Just me · guess Device & Software › Computer problem)*

**You'll see:** ⬆️ **ESCALATE → Security**, **P1**, Security › Virus 85%. Chip *"You chose Device & Software — model says
Security"*. Similar tickets are ransom-note cases. Fix from **KB-051**: containment first (*"Don't click anything
else, and disconnect from the network if asked"*).

**Say:** "The first symptom word is 'slow'. A keyword system would file this as a performance ticket. The model reads
the whole sentence and sends it to Security as P1."

### 2h. (Optional, 20 s) Past tickets
Click **Past tickets** in the menu: 1,200 tickets with filters (service, category, priority, team, environment, who is
affected, text search) and a masked CSV export. Labels are marked *"Generated labels"*.

---

## Feature 3: Admin (⚙️ Admin)

Set **Viewing as → Admin**.

| Page | Show | Say |
|---|---|---|
| 💬 **Feedback & audit** | Set **Support person** to your name. Your **Useful** click from 2b is there. The **Knowledge gaps** count includes the website-prices ticket. Scroll to the audit records → CSV / JSON export. | "Every analysis is stored: input, labels, evidence, fix, decision. Exports have personal data masked." |
| 📊 **Evaluation** | KPI row → **Hype resistance** and **Security safety net** cards → confusion-matrix tabs (Category / Symptom type / Priority) → **keyword vs vector vs hybrid** table → **Fallback: 17 / 17** probe tickets sent to a human. | "On 180 held-out tickets: category 96.1%, priority 98.9%. Vector search beat keyword and hybrid, *measured* (MRR 0.955 vs 0.862 for keyword). Every weak or contradictory probe went to a human." |
| ⏱️ **MTTR** | The blue **Simulated baseline** banner (P1 4 h · P2 8 h · P3 1 day · P4 2 days) → **Overall time reduction** (66.8% today) → baseline vs assisted chart per priority. | "Our data has no real resolution history, so the manual baseline is **simulated**, and we label it that way. The VPN ticket I just marked resolved is in here, with real timestamps." |
| 📚 **Knowledge base** | Pick **KB-020**: self-help steps vs support steps, each with an ID such as `KB-020/self/1`. | "These IDs are exactly what the fix cites. 55 articles: 33 public, 22 internal." |
| 🔑 **Settings** | Active LLM, failover order (every Groq key → every Gemini key → local Ollama), key shown masked, system status. | "If every route fails, the ticket is escalated. The system never guesses." |

> **Be honest about MTTR:** 60 of the resolved records are seeded demo data (analyst *"Simulated demo data"*,
> ids `DEMO-…`). Don't present 66.8% as a real measurement.

---

## Closing line (30 s)

> "Three features, one rule: **evidence or escalate**. Every label has a probability or a rule reason, every fix step
> has a checked citation, and anything weak (low confidence, disagreement, a possible security issue, missing
> knowledge or a vague ticket) goes to a human."

---

## 4. Avoid on stage

| Don't | Why | Do instead |
|---|---|---|
| Do the hype test on a printer ticket (e.g. faint prints) with the LLM on | We removed the old *Calm vs hype (printer)* button for this reason. Calm gave **NEED INFO** and hype gave **ESCALATE (knowledge gap)** in testing. Priority was P3 both times, but the LLM couldn't decide whether a printer article fits, so it *looks* as if hype changed the result. | Use **VPN on, shared drive off** + the hype toggle (2c). Same result both times, tested twice. |
| Type "I can't sign in to my laptop" under Laptop / Desktop | Known limit: it's misread as Security P1, because every sign-in ticket in our data uses Company Login. Safe (a human reviews it) but wrong. | If a judge tries it, say so. It's in README §7. |
| Present the MTTR % as real | Both the baseline and the 60 seeded records are simulated. | Point at the ticket you resolved live. |

---

## 5. Backup plan

| Problem | What to do |
|---|---|
| LLM down or rate-limited (sidebar 🔴) | Untick **Write a cited fix with the LLM**. Classification, similar tickets and KB search still work in under 1 s. Tickets that would get a fix become ESCALATE *"no fix written (LLM switched off)"*. Vague → still NEED INFO; uncovered → still knowledge gap. Say: "No LLM, no fix, so it escalates. It never guesses." Then show the cited fixes in `reports/EXAMPLES.md`. |
| First analysis is slow | That's the models loading once. Open **Trace** afterwards to show per-step times. |
| A page shows a red "missing" status | Run the command shown on the page (`python -m build.train_models` or `python -m build.build_index`). |

---

## 6. Likely judge questions

| Question | Short answer |
|---|---|
| Why not use an LLM to classify? | Logistic regression is fast (~0.15 s), free and measurable, and gives real probabilities. Low scores go to REVIEW anyway. |
| How do you stop hallucinated fixes? | The LLM may only write from retrieved KB articles. Code checks each step against the sentence it cites and drops any that don't match: 100% citation validity. No article → no fix → escalate. |
| Where is duplicate detection? | **Similar past tickets** tab: vector search on meaning plus the same-service signal, with a vote and a **Possible duplicate** badge. Hit@5 100%, MRR 0.955. |
| Why vector and not hybrid search? | We measured both. Our tickets paraphrase a lot, so exact keywords added noise (MRR 0.955 vs 0.917). |
| What if the model is wrong? | Disagreement, low confidence, a possible security issue or a knowledge gap → REVIEW or ESCALATE. Analysts mark results Useful / Incorrect / Unresolved, and Admin sees it per article. |
| Can the user game the priority? | No. Priority uses facts only (service, environment, who is affected, symptom). Hype test: 168 / 168 unchanged. |
| Biggest limitation? | A valid citation isn't the same as the right article (INC-00073 in EXAMPLES.md: real steps, partial fit). Feedback and the human gates are the safeguard. |
| Is the data real? | No. It's synthetic and generated by us, and that's labelled everywhere. Prompts are in `Prompts/`. |
