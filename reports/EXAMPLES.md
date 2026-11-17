# ResolveIQ — Worked Examples

Six tickets run through the **real pipeline** (`src/pipeline.analyze_ticket`, role = Support) on 2026-11-17.
The fix writer used Groq `openai/gpt-oss-120b`. The full raw output of each run, with every score, is in
[`examples_results.json`](examples_results.json). To regenerate both: `python -m build.run_examples`. LLM wording can
change slightly between runs, but the citations are always checked by code.

| # | Ticket | What it shows | Outcome |
|---|---|---|---|
| 1 | INC-00073 (held out) | everything agrees → confident cited fix | ✅ RECOMMEND |
| 2 | INC-00040 (held out) | user picked the wrong category → model corrects it, a human checks | 👀 REVIEW |
| 3 | INC-00347 (held out) + hype | hype removed, wrong user category corrected, P2 from facts | ⬆️ ESCALATE |
| 4 | Probe: ransomware on a laptop | security spotted from the text alone → P1 to Security | ⬆️ ESCALATE |
| 5 | Probe: wrong prices on the website | no KB article for this → knowledge gap, no invented fix | ⬆️ ESCALATE |
| 6 | Probe: "System not working" | too vague → questions for the user | ❓ NEED INFO |

*Held out* = in the 15% test split, never used for training and not in the search index. *Probe* = hand-written
by us to test fallback (see `reports/RAG_EVALUATION.md` §4). All labels in the dataset are **generated**.

Each example follows the same order as the brief asks: **input → classification → similar cases → recommended
resolution → source evidence**, followed by our own check of the result.

---

## 1. INC-00073: shared calendar request → ✅ RECOMMEND

**Input**
> *"Could we get a single calendar for both daytime operations crews and the separate evening intake group?"*
> Service: Email · Production · Many teams · user's guess: Email & Communication › Calendar problem

**Classification** (true labels in brackets, all match)

| Field | Prediction | Confidence / reason |
|---|---|---|
| Category | Email & Communication | 98.1% · combined score 0.99 (model + 5/5 similar tickets + user agree) |
| Subcategory | Calendar problem | 90.7% (next: Email problem 8.1%) |
| Symptom type | request | 96.0% |
| Team | Applications | rule |
| Priority | **P3** [P3] | *impact High (many teams, critical service) × urgency Low (request, production)* |

**Similar past tickets** (top 3 of 5, all Calendar problem)

| Ticket | Score | Why matched | Excerpt |
|---|---|---|---|
| INC-00006 | 0.66 | similar by meaning · same service: Email | "Please create a shared leave calendar for the crews covering reception and stock…" |
| INC-00170 | 0.62 | similar by meaning · same service: Email | "Could you make a calendar just for our group's Tuesday training sessions?" |
| INC-00111 | 0.60 | similar by meaning · same service: Email | "Can my team have one shared bookings calendar for the new workroom?" |

**Recommended resolution**: path from **KB-016 *How to share my work calendar with a coworker*** (public).
*Why it fits (LLM):* "The request is to create a shared calendar for two groups, which is addressed by the calendar sharing article."

| # | Step | Cites | Source evidence (quoted from the KB) |
|---|---|---|---|
| 1 | Open your work calendar in webmail and select Share on your own calendar. | `KB-016/self/1` | identical |
| 2 | Enter your coworker's company address and confirm the address shown. | `KB-016/self/2` | identical |
| 3 | Select Can view when I'm busy and send the invitation. | `KB-016/self/3` | identical |
| 4 | Ask the coworker to open your calendar and confirm they see your availability. | `KB-016/self/4` | identical |
| 5 | Confirm that the employee owns the selected calendar and the recipient is an eligible company account. | `KB-016/support/1` | identical · *Expected: The share is for the intended calendar and coworker.* |
| 6 | Have the employee review the permission list and select availability only for that recipient. | `KB-016/support/2` | identical · *Expected: The entry grants busy and free visibility only.* |
| 7 | Check the calendar from the recipient's side with a test event that contains no real meeting details. | `KB-016/support/3` | identical · *Expected: The recipient sees the time block and cannot see the test event's details.* |

Support steps in the KB also carry an *expected result*, which the analyst sees next to each step so they can tell
whether it worked. The same holds for every support step in the examples below (shown in full in the JSON file).

Citation validity **100%** (7 / 7 kept). Decision: *"classifier, similar tickets and KB agree (confidence 79%)"*.

**Our check: classification right, fix only a partial fit.** The user wants a *new shared group calendar*. KB-016
explains *sharing your own calendar with one coworker*. The steps are real and cited, but they don't fully answer
the request. The KB has no "create a group calendar" article (best KB match was only 0.38). This is the kind of
case the analyst's **Incorrect / Unresolved** feedback is for, and it shows a known limit: a citation check proves
a step *comes from* the article. It can't prove the article is the *right* one.

---

## 2. INC-00040: wrong user category → 👀 REVIEW

**Input**
> *"the test self-service page won't send my password reset message. i can't get into the sandbox."*
> Service: Company Login · **Test** · Just me · user's guess: **Business System › Error or won't open**

**Classification** (true: Account & Access › Password reset · blocked · Service Desk · P3, all match)

| Field | Prediction | Confidence / reason |
|---|---|---|
| Category | **Account & Access** | 74.7% (next: Business System 24.5%) · combined score **0.65** because the user disagreed |
| Subcategory | Password reset | 86.3% |
| Symptom type | blocked | 97.3% |
| Team | Service Desk | rule |
| Priority | **P3** [P3] | *impact Medium (just me, critical service) × urgency Medium (blocked, **test**)* |

The same problem in Production would be more urgent. Here the environment is Test, so urgency drops to Medium.

**Similar past tickets** (5 / 5 vote Account & Access)

| Ticket | Score | Subcategory | Excerpt |
|---|---|---|---|
| INC-01070 | 0.75 | Password reset | "The restored login sandbox asks me to choose a password but rejects every reset attempt…" |
| INC-01086 | 0.73 | Password reset | "My sandbox password has expired, and there's no reset address on that test account…" |
| INC-00690 | 0.67 | Account locked | "My sandbox identity has a lockout flag even though I stopped the invalid login requests…" |

**Recommended resolution**: path from **KB-002 *Password reset link says it has expired***.
*Why it fits (LLM):* "The reset message never arrives, which matches the escalation condition of KB-002."

| # | Step | Cites |
|---|---|---|
| 1 | Compare reset issuance and redemption timestamps for the employee's account without collecting the reset URL. | `KB-002/support/1` |
| 2 | Initiate one reset through the verified account workflow if the employee cannot issue one. | `KB-002/support/2` |
| 3 | Have the employee open the newest message privately and confirm the completion event. | `KB-002/support/3` |

Citation validity **100%** (3 / 3, each step quoted word for word from the article). Decision: **REVIEW**, *"user chose
'Business System', model says 'Account & Access'"*.

**Our check: correct.** The model fixed the user's category, and the similar tickets backed it up independently.
The system still asks a human to confirm rather than silently overriding the user. Step 2 (issue a fresh reset
through the verified workflow) is the useful action for "the message never arrives".

---

## 3. INC-00347 + hype: hype ignored, P2 from facts → ⬆️ ESCALATE

**Input** (a held-out ticket with one hype sentence added by us)
> *"I'm getting heat from above. Please pick this up immediately. My workng salary application closes just after
> login. I can see the menu for a moment but can't open a run."*
> Service: Payroll System · Production · Just me · user's guess: **Device & Software › Install software**

**Step 2, cleaning:** the hype sentences are detected (`hype_detected = true`, shown to the analyst as a chip) and
**removed before classification**. The model only reads *"my workng salary application closes just after login…"*.

**Classification** (true: Business System › Error or won't open · blocked · Applications · P2, all match)

| Field | Prediction | Confidence / reason |
|---|---|---|
| Category | **Business System** | 97.1% · combined score 0.78 (user disagreed) |
| Subcategory | Error or won't open | 96.8% |
| Symptom type | blocked | 60.3% (next: slow 28.3%) |
| Team | Applications | rule |
| Priority | **P2** [P2] | *impact Medium (just me, critical service) × urgency High (blocked, production)* |

The priority comes from *who is affected, which service, which environment and the symptom*. "Pick this up
immediately" plays no part. Our injection test showed the same on 168 / 168 tickets (`reports/EVALUATION.md` §3).

**Similar past tickets** (5 / 5 vote Business System, all same service)

| Ticket | Score | Excerpt |
|---|---|---|
| INC-00552 | 0.59 | "The production salary dashboard is frozen at 'restoring prior session' for my profile…" |
| INC-00251 | 0.54 | "Since I imported my batch the live payroll console won't open my workspace at all…" |
| INC-00922 | 0.53 | "The payroll home page opens to a fatal backend error…" |

**Recommended resolution**: path from **KB-030 *Payroll System is down for everyone after sign-in*** (internal).

| # | Step | Cites |
|---|---|---|
| 1 | Compare failure times across independent authorized users and run the non-mutating Payroll System health checks. | `KB-030/support/1` |
| 2 | Review the Payroll System connection-pool health and dependency errors using request IDs. | `KB-030/support/2` |
| 3 | Page the Payroll System owner with the dependency state and current processing window, and have them follow the approved recovery procedure. | `KB-030/support/3` |
| 4 | Repeat read-only health checks and reconcile pending job identifiers with the owner before any replay. | `KB-030/support/4` |

Citation validity **100%**. Decision: **ESCALATE** to Applications, *"P2: … the cited fix is attached"*.

**Our check: right team, right priority, fix partly fits.** KB-030 is for an outage affecting *everyone*, while this
ticket affects *just me*. Step 1 (check whether other users are affected) is still the right first move, and it tells
the engineer which case they're in. Because it's P2, a human owns it anyway. The fix is attached to save time, not
to act on blindly.

---

## 4. Probe: ransomware on a laptop → ⬆️ ESCALATE (P1, Security)

**Input** (no user category given)
> *"My laptop got very slow after I opened an invoice attachment, and now a window says my files are encrypted and
> asks for payment."*
> Service: Laptop / Desktop · Production · Just me

**Classification**

| Field | Prediction | Confidence / reason |
|---|---|---|
| Category | **Security** | 91.7% (next: Device & Software 7.3%) |
| Subcategory | Virus | 85.0% |
| Symptom type | blocked | 49.7% (slow 49.3%: a near tie) |
| Team | **Security** | rule |
| Priority | **P1** | *impact High × urgency High (blocked, production)*. Security raises the impact even for one person |

The word "slow" comes first in the text. A keyword system would treat it as a performance ticket. The model reads
the whole sentence (attachment → encrypted files → payment) and puts it in Security.

**Similar past tickets** (3 / 5 vote Security)

| Ticket | Score | Excerpt |
|---|---|---|
| INC-00718 | 0.44 | "My working files now end in .grindle and there's a ransom note on the desktop…" |
| INC-00666 | 0.42 | "my screen is stuck on a demand to pay for a decryption key…" |
| INC-00362 | 0.40 | "A file I downloaded started renaming all my project folders. There's a payment note in each…" |

**Recommended resolution**: path from **KB-051 *The work computer quarantined a file opened from an attachment*** (internal).

| # | Step | Cites |
|---|---|---|
| 1 | Don't click anything else, and disconnect from the network if asked | `KB-051/self/1` |
| 2 | Contact the help desk from a separate trusted device and report the alert time and computer name. | `KB-051/self/2` |
| 3 | Leave the file quarantined and tell support whether you opened it before the alert appeared. | `KB-051/self/3` |
| 4 | Match the device and timestamp to the endpoint security event and preserve the relevant file identifier, process trail and action status. | `KB-051/support/1` |
| 5 | Review execution and connection telemetry for the time around the alert, then have Security isolate the device through the approved workflow if indicated. | `KB-051/support/2` |
| 6 | Search approved mail and endpoint telemetry for the same file identifier and sender indicators. | `KB-051/support/3` |
| 7 | Have Security direct remediation and check the endpoint again before restoring normal use. | `KB-051/support/4` |

Citation validity **100%**. Decision: **ESCALATE** to Security, *"P1: a Security engineer owns it; the cited fix is attached"*.

**Our check: correct and the most important case to get right.** Containment comes first (stop, disconnect,
report from another device) and Security isolates the device through the approved workflow. The assistant itself
takes no action on the laptop. Two of the three KB matches (KB-026, KB-024) were network articles pulled in by
"laptop" + "slow". The LLM ignored them and wrote the fix from KB-051 only.

---

## 5. Probe: wrong prices on the website → ⬆️ ESCALATE (knowledge gap)

**Input**
> *"Customers see the wrong prices on the company website product pages."*
> Service: Company Website · Production · Customers

**Classification**: Business System › **Wrong data** (88.6%) · team Applications · **P2** (*impact High:
customers × urgency Medium*). Similar tickets: INC-00801 (0.46), INC-00371 (0.41), INC-00606 (0.39), all *Wrong
data* on Company Website, 5 / 5 vote Business System.

**KB search**

| Article | Score | Why it doesn't apply |
|---|---|---|
| KB-035 *Finance System dashboard is still showing yesterday's figures* | 0.28 | right subcategory, **wrong service** |
| KB-034 *Company Website opens but images load slowly…* | 0.31 | right service, wrong problem |
| KB-031 *Company Website is down for customers with a certificate warning* | 0.30 | right service, wrong problem |

**Recommended resolution: none, on purpose.** No article is written for *Wrong data* on *Company Website* (this
gap was left in the KB deliberately). The fix writer is **not called**, so no steps can be invented.

Decision: **ESCALATE** to Applications, *"knowledge gap: no KB article covers 'Wrong data' on Company Website"*.
Confidence 42%. The gap is logged for Admin as an article to write.

**Our check: correct behaviour.** A similar-sounding Finance article exists, and a naive RAG system would have
"answered" from it. One weak spot: the symptom was predicted as *slow* (79%), which doesn't really describe wrong
prices. It didn't change the outcome here, but it shows the symptom model has never seen this kind of ticket.

---

## 6. Probe: "System not working, please help." → ❓ NEED INFO

**Input**
> *"System not working, please help."* · Service: Other / Not sure · Production · Just me

**Cleaning:** the completeness check marks it **too vague** (no service, no symptom detail).

**Classification** (shown for transparency, not trusted): Device & Software › Computer problem. The subcategory is
only 51%, with Printer problem 24% and Install software 23% close behind. Similar tickets (INC-00103, INC-00605,
INC-00201) only score 0.36–0.41, and the best KB match is 0.23.

**Recommended resolution: none.** Instead, two questions to send back to the user:
1. *Which application, device or service is affected?*
2. *What exactly happens, and is there an error message?*

Decision: **NEED INFO**, confidence 40%.

**Our check: correct.** The classifier still gives a confident-looking *category* (93.9%) because "not working"
appears most often in computer tickets. That's why vagueness is checked on the text **before** the classifier's
score is trusted.

---

## What these examples show (and don't)

| Brief dimension | Evidence here |
|---|---|
| Classification quality | 3 / 3 held-out tickets fully correct (category, subcategory, symptom, team, priority) |
| Duplicate retrieval | similar tickets match on meaning, not shared words (e.g. "sandbox password expired" for "reset message won't send") |
| Resolution usefulness | 2 good fixes (#2, #4), 2 partial fits (#1, #3), and 2 cases correctly given no fix (#5, #6) |
| Confidence and fallback | wrong user category → REVIEW · P1 / P2 → ESCALATE · knowledge gap → ESCALATE · vague → NEED INFO |
| Traceability | every label has a probability or rule reason · every fix step cites `KB-xxx/self` or `KB-xxx/support/n`, and its action text matches the cited source word for word (21 / 21 steps; in #3 the LLM swapped plain hyphens for non-breaking ones) |

**Limits these examples show honestly:**
- **A valid citation isn't the same as the right article.** #1 and #3 cite real steps from articles that only partly
  fit. The analyst's feedback buttons, and the REVIEW / ESCALATE gates, are the safeguard.
- **Speed:** the first ticket took ~8 s for similar-ticket search because the embedding model was loading. After
  that, each analysis is ~0.2–0.5 s before the LLM and ~2–2.5 s for the LLM fix.
- 6 examples are a sample. The measured rates are in `reports/EVALUATION.md` and `reports/RAG_EVALUATION.md`.
