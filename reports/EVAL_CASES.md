# ResolveIQ — Evaluation questions vs expected answers

Run on 2026-11-17 16:05 through the real pipeline (same functions and roles the app uses). Cases and expected answers: [`data/eval_cases.json`](../data/eval_cases.json). Regenerate: `python -m build.run_eval_cases --runs 3`.

**33 / 38 cases match their expected answer in all 3 runs**. A case passes only if every checked field matches; ✅* = passes, with one documented known miss (listed at the end, never hidden).

How the expected answers were decided: held-out tickets use the dataset's true labels (never trained on, not in the search index) and the decision table in `src/decide.py`; probes use the rules in `src/rules.py`, worked out by hand; the expected KB article was chosen by reading the titles.

## Tickets (New ticket page, role Support)

| ID | Case | Expected | Actual | Priority | Fix from | Result |
|---|---|---|---|---|---|---|
| T01 | App example 'VPN on, shared drive off' | RECOMMEND | RECOMMEND | P3 | KB-020 | ✅ 3/3 |
| T02 | T01 + the 'URGENT - I'm the CEO' hype toggle | RECOMMEND | RECOMMEND | P3 | KB-020 | ✅ 3/3 |
| T03 | App example 'INC-00347 - hype + wrong guess' (held out) | ESCALATE | ESCALATE | P2 | KB-030 | ✅ 3/3 |
| T04 | App example 'Calm vs hype (printer)' | ESCALATE | ESCALATE | P3 | – | ✅* 3/3 |
| T05 | T04 + the hype toggle | ESCALATE | NEED_INFO | P3 | – | ❌ 2/3 |
| T06 | App example 'Vague ticket' | NEED_INFO | NEED_INFO | P4 | – | ✅ 3/3 |
| T07 | App example 'Uncovered problem' | ESCALATE | ESCALATE | P2 | – | ✅ 3/3 |
| T08 | INC-00073 shared calendar request (held out) | RECOMMEND | RECOMMEND | P3 | KB-016 | ✅* 3/3 |
| T09 | INC-00100 password reset request (held out) | RECOMMEND | RECOMMEND | P4 | KB-001 | ✅ 3/3 |
| T10 | INC-00852 account locked in a TEST environment (held out) | RECOMMEND | RECOMMEND | P3 | KB-004 | ✅ 3/3 |
| T11 | INC-00961 VPN slow to set up routes (held out) | RECOMMEND | RECOMMEND | P4 | KB-021 | ❌ 2/3 |
| T12 | INC-00717 Wi-Fi drops at my desk (held out) | RECOMMEND | RECOMMEND | P4 | KB-025 | ✅ 3/3 |
| T13 | INC-00333 external monitors go dark (held out) | RECOMMEND | RECOMMEND | P3 | KB-037 | ✅ 3/3 |
| T14 | INC-00401 Finance report slow on a month-end date (held out) | RECOMMEND | RECOMMEND | P3 | KB-032 | ✅ 3/3 |
| T15 | INC-00392 Finance wrong data + threat to go to the director (held out) | RECOMMEND | RECOMMEND | P4 | KB-035 | ❌ 1/3 |
| T16 | INC-01193 'Need a PDF tool installed' (held out) | RECOMMEND | NEED_INFO | P4 | – | ❌ 2/3 |
| T17 | INC-00040 user picked the wrong category (held out) | REVIEW | REVIEW | P3 | KB-002 | ✅ 3/3 |
| T18 | INC-00567 meeting app drops when choosing the microphone (held out) | REVIEW | REVIEW | P3 | KB-013 | ❌ 1/3 |
| T19 | Probe: two problems in one ticket | REVIEW | REVIEW | P4 | KB-020 | ✅ 3/3 |
| T20 | INC-00267 account locked in PRODUCTION (held out) | ESCALATE | ESCALATE | P2 | KB-004 | ✅ 3/3 |
| T21 | INC-00036 email down for the whole company (held out) | ESCALATE | ESCALATE | P1 | KB-012 | ✅ 3/3 |
| T22 | INC-00997 shared label printer rejects every job (held out) | ESCALATE | ESCALATE | P2 | KB-040 | ✅ 3/3 |
| T23 | INC-00474 'Weird email with a login button. Real?' (held out) | ESCALATE | ESCALATE | P1 | KB-049 | ✅ 3/3 |
| T24 | Probe: ransomware described as 'slow laptop' | ESCALATE | ESCALATE | P1 | KB-051 | ✅ 3/3 |
| T25 | Probe: re-submit indexed ticket INC-00408 (VPN down for everyone) | ESCALATE | ESCALATE | P1 | KB-022 | ✅ 3/3 |
| T26 | INC-00802 payroll summary shows the wrong division (held out) | ESCALATE | ESCALATE | P4 | – | ✅ 3/3 |
| T27 | INC-00758 shared folder slow to show versions (held out) | ESCALATE | ESCALATE | P4 | – | ✅ 3/3 |
| T28 | Probe: personal data in the description | REVIEW | REVIEW | P4 | KB-010 | ✅ 3/3 |

## Questions (KB Assistant, role Employee)

| ID | Question | Expected | Actual | Top source | Steps cite | Result |
|---|---|---|---|---|---|---|
| K01 | I forgot my password | answered | answered | KB-001 | KB-001 | ✅ 3/3 |
| K02 | VPN connects but shared drives won't open | answered | answered | KB-020 | KB-020 | ✅ 3/3 |
| K03 | How do I share my calendar? | answered | answered | KB-016 | KB-016 | ✅ 3/3 |
| K04 | Outlook keeps asking for my password | answered | answered | KB-010 | KB-010 | ✅ 3/3 |
| K05 | My work phone isn't charging | answered | answered | KB-043 | KB-043 | ✅ 3/3 |
| K06 | I got an email asking me to sign in through a link. Is it safe? | answered | answered | KB-049 | KB-049 | ✅ 3/3 |
| K07 | My work computer has no space left to save files | not answered | not answered | KB-001 | – | ✅ 3/3 |
| K08 | Customers see the wrong prices on the company website | not answered | not answered | KB-035 | – | ✅ 3/3 |
| K09 | What is on the canteen lunch menu today? | not answered | not answered | KB-035 | – | ✅ 3/3 |
| K10 | help | not answered | not answered | KB-002 | – | ✅ 3/3 |

## Mismatches

- **T05** run 1: outcome: expected 'ESCALATE', got 'NEED_INFO'
- **T05** run 1: escalate_to: expected 'Desktop Support', got None
- **T05** run 1: knowledge_gap: expected True, got False
- **T11** run 2: outcome: expected 'RECOMMEND', got 'NEED_INFO'
- **T11** run 2: fix_from: expected 'KB-021', got []
- **T15** run 2: outcome: expected 'RECOMMEND', got 'ESCALATE'
- **T15** run 2: knowledge_gap: expected False, got True
- **T15** run 2: fix_from: expected 'KB-035', got None
- **T15** run 3: outcome: expected 'RECOMMEND', got 'ESCALATE'
- **T15** run 3: knowledge_gap: expected False, got True
- **T15** run 3: fix_from: expected 'KB-035', got None
- **T16** run 1: outcome: expected 'RECOMMEND', got 'NEED_INFO'
- **T16** run 1: fix_from: expected ['KB-046', 'KB-047'], got []
- **T18** run 2: outcome: expected 'REVIEW', got 'NEED_INFO'
- **T18** run 2: reasons should contain ["user chose 'Device & Software'"]; got 'not enough detail to act on; ask the user the questions below'
- **T18** run 3: outcome: expected 'REVIEW', got 'NEED_INFO'
- **T18** run 3: reasons should contain ["user chose 'Device & Software'"]; got 'not enough detail to act on; ask the user the questions below'

## Known misses (the expected value is the right answer; the app differs on this field)

- **T04** `symptom_type` (differs in 3/3 runs): The app shows 'blocked'. The data spec says a workaround means 'slow', so 'slow' is the right answer and this is a model miss. It is harmless here: my team + not Production gives P3 either way.
- **T05** `symptom_type` (differs in 3/3 runs): Same model miss as T04: the app shows 'blocked'; the right answer is 'slow'. Priority is P3 either way.
- **T08** `top_kb` (differs in 3/3 runs): Search ranks KB-018 ('meeting at the wrong time after travelling') first and KB-016 second. The fix is still written from KB-016, because the LLM picks the article that fits from the top 3. A ranking miss at #1, not a wrong answer.
