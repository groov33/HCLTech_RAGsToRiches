# ResolveIQ — Search (RAG) Evaluation

Held-out test set: **180 tickets**, never in the search index. A result counts as relevant when it has the ticket's true subcategory (an automatic stand-in for hand labels).

## 1. Similar past tickets

| Search | Hit@5 | Precision@5 | MRR |
|---|---|---|---|
| keyword | 96.7% | 64.6% | 0.862 |
| vector | 100.0% | 83.2% | 0.955 |
| hybrid | 98.3% | 76.4% | 0.917 |

## 2. KB articles

| Search | Hit@1 | Hit@3 | Hit@1 with classifier hint | Hit@3 with hint |
|---|---|---|---|---|
| keyword | 64.4% | 77.2% | **84.4%** | **87.2%** |
| vector | 71.7% | 83.9% | **88.3%** | **93.9%** |
| hybrid | 70.0% | 81.7% | **84.4%** | **89.4%** |

*Hint* = the predicted subcategory boosts matching articles by up to 20% (never filters).

## 3. Full pipeline (with LLM)

- Tickets run: 10 · average citation validity: **100.0%** · LLM: groq:openai/gpt-oss-120b, None

| Ticket | Decision | Steps kept / written | Reason |
|---|---|---|---|
| INC-00013 | ESCALATE | 0 / 0 | knowledge gap: no KB article is close to this ticket, handing to Applications |
| INC-00022 | ESCALATE | 0 / 0 | knowledge gap: the LLM found no article that really fits, handing to Applications |
| INC-00030 | ESCALATE | 4 / 4 | P2: a Applications engineer owns it; the cited fix is attached |
| INC-00036 | ESCALATE | 4 / 4 | P1: a Applications engineer owns it; the cited fix is attached |
| INC-00040 | REVIEW | 3 / 3 | user chose 'Business System', model says 'Account & Access' |
| INC-00061 | ESCALATE | 0 / 0 | knowledge gap: the LLM found no article that really fits, handing to Desktop Support |
| INC-00062 | ESCALATE | 0 / 0 | knowledge gap: the LLM found no article that really fits, handing to Desktop Support |
| INC-00068 | ESCALATE | 0 / 0 | knowledge gap: no KB article covers 'Need access' on Company Website, handing to Service Desk |
| INC-00070 | ESCALATE | 0 / 0 | LLM unavailable: handing to Applications with the evidence found |
| INC-00073 | RECOMMEND | 4 / 4 | classifier, similar tickets and KB agree (confidence 79%) |

## 4. Weak or contradictory evidence (probe tickets)

17 hand-written tickets that should **not** get a confident answer. Pass = the outcome is ESCALATE, REVIEW or NEED_INFO (a clarification request), i.e. a human sees it before anything happens. RECOMMEND = a miss.

**Sent to a human: 16 / 17 (94.1%)**

| Kind | Passed |
|---|---|
| knowledge gap | 3 / 3 |
| too vague | 3 / 3 |
| off-topic | 3 / 3 |
| contradictory fields | 2 / 2 |
| two problems | 1 / 2 |
| hidden security | 2 / 2 |
| wrong user category | 2 / 2 |

| Kind | Ticket | Service | Decision | Human? | Reasons |
|---|---|---|---|---|---|
| knowledge gap | Customers see the wrong prices on the company website product pages. | Company Website | ESCALATE | ✅ | knowledge gap: no KB article covers 'Wrong data' on Company Website, handing to Applications |
| knowledge gap | My salary this month is lower than it should be, one allowance is missing. | Payroll System | ESCALATE | ✅ | knowledge gap: no KB article covers 'Wrong data' on Payroll System, handing to Applications |
| knowledge gap | Every printer on the third floor prints blank pages since this morning. | Printer | NEED_INFO | ✅ | not enough detail to act on; ask the user the questions below |
| too vague | System not working, please help. | Other / Not sure | NEED_INFO | ✅ | not enough detail to act on; ask the user the questions below |
| too vague | It's broken again. | Other / Not sure | NEED_INFO | ✅ | not enough detail to act on; ask the user the questions below |
| too vague | Having some issues since yesterday, can someone take a look? | Other / Not sure | NEED_INFO | ✅ | not enough detail to act on; ask the user the questions below |
| off-topic | The coffee machine in the second floor kitchen is leaking water onto the floor. | Other / Not sure | ESCALATE | ✅ | knowledge gap: no KB article is close to this ticket, handing to Service Desk |
| off-topic | Can I book the large meeting room for our team lunch on Friday? | Other / Not sure | ESCALATE | ✅ | knowledge gap: the LLM found no article that really fits, handing to Service Desk |
| off-topic | The air conditioning in our open-plan office has been far too cold all week. | Other / Not sure | ESCALATE | ✅ | knowledge gap: the LLM found no article that really fits, handing to Service Desk |
| contradictory fields | The office Wi-Fi keeps dropping my laptop every few minutes and I have to reconnect each time. | Payroll System | REVIEW | ✅ | unsure about category (score 65%); classifier says 'Error or won't open', best article is about 'Wi-Fi problem' |
| contradictory fields | The printer next to my desk jams on every page and shows a paper feed error. | Email | ESCALATE | ✅ | LLM unavailable: handing to Applications with the evidence found |
| two problems | The VPN drops every few minutes and separately my email stopped syncing on my phone since this morning. | VPN | RECOMMEND | ❌ | classifier, similar tickets and KB agree (confidence 81%) |
| two problems | My laptop will not charge any more and the printer on my floor prints blank pages. | Laptop / Desktop | ESCALATE | ✅ | LLM unavailable: handing to Desktop Support with the evidence found |
| hidden security | My laptop got very slow after I opened an invoice attachment, and now a window says my files are encrypted and asks for payment. | Laptop / Desktop | ESCALATE | ✅ | P1: a Security engineer owns it; the cited fix is attached |
| hidden security | I entered my password on a page linked from an email about my mailbox being full, and now I can't sign in to email. | Email | ESCALATE | ✅ | LLM unavailable: handing to Applications with the evidence found |
| wrong user category | I can't print the payroll report: the printer says it is offline although it is switched on. | Printer | ESCALATE | ✅ | knowledge gap: the LLM found no article that really fits, handing to Desktop Support |
| wrong user category | My work account got locked after too many password attempts this morning. | Company Login | ESCALATE | ✅ | P2: a Service Desk engineer owns it; the cited fix is attached |
