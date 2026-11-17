# Data Generation Prompt — ResolveIQ Ticket Corpus

Copy everything below the line into the AI that will generate the data.
(The knowledge base is generated separately.)

---

You are generating a **synthetic IT help-desk ticket dataset** for a company. Each ticket has fields the **user fills in** and fields the **system must predict** (the correct answers). All names and details must be fake. Use only the allowed values below.

## PART 1 — What the user fills in (INPUT fields)

| Field | Type | Allowed values | Can the user get it wrong? |
|---|---|---|---|
| `description` | free text, 1–6 sentences | anything | **Yes.** May exaggerate ("URGENT!!!", "I'm the CEO", "whole company depends on this") |
| `service` | dropdown | Service list (Part 3) | No, treat as true |
| `environment` | dropdown | `Production`, `Test`, `Not applicable` | No, treat as true |
| `who_affected` | dropdown | `Just me`, `My team`, `Many teams`, `Customers` | No, treat as true |
| `user_category` | dropdown | Category list (Part 3) | **Yes**, about 20 % of the time it is wrong |
| `user_subcategory` | dropdown | must belong to `user_category` | **Yes**, follows `user_category` |

### `environment`
| Value | Meaning |
|---|---|
| `Production` | the real, live system people use for their daily work |
| `Test` | a practice copy of a system used to try changes before going live |
| `Not applicable` | personal devices and office equipment (laptop, printer, phone, Wi-Fi) |

### `who_affected`
| Value | Meaning |
|---|---|
| `Just me` | only the person writing the ticket |
| `My team` | the writer's own team (about 2–50 people) |
| `Many teams` | several departments, a whole office or the whole company |
| `Customers` | people outside the company, e.g. clients using the company website |

## PART 2 — What the system must predict (ANSWER fields)

| Field | Allowed values | How to set it |
|---|---|---|
| `category` | Category list | the TRUE category (equals `user_category` ~80 % of the time) |
| `subcategory` | Subcategory list | the TRUE subcategory |
| `team` | Teams list | routing rule (Part 4) |
| `symptom_type` | `outage`, `blocked`, `slow`, `request`, `question` | what is really happening (Part 3) |
| `impact` | `High`, `Medium`, `Low` | impact rule (Part 4) |
| `urgency` | `High`, `Medium`, `Low` | urgency rule (Part 4) |
| `priority` | `P1`, `P2`, `P3`, `P4` | impact × urgency matrix (Part 4) |

**The answer fields must follow the facts (service, environment, who_affected, the real problem), never the tone of the description.**

## PART 3 — Reference lists

### Services (14)
| Service | What it is | Importance | Team that owns it |
|---|---|---|---|
| Email | sending and receiving work email | Critical | Applications |
| Company Login | the username and password used for everything | Critical | Service Desk |
| VPN | connecting to the office network from home | Critical | Network |
| Finance System | accounts, invoices, month-end closing | Critical (busiest in the last 3 days of the month) | Applications |
| Payroll System | paying salaries | Critical (busiest on the 25th–30th) | Applications |
| Company Website | the website customers use | Critical | Applications |
| Chat & Video Calls | instant messages and online meetings | Important | Applications |
| Shared Files | shared drives and online folders | Important | Applications |
| Office Wi-Fi | wireless internet in the office | Important | Network |
| Laptop / Desktop | the user's own computer | Minor | Desktop Support |
| Printer | office printers and scanners | Minor | Desktop Support |
| Mobile Phone | company phone | Minor | Desktop Support |
| Software Install | installing or updating programs | Minor | Desktop Support |
| Other / Not sure | anything else | Minor | Service Desk |

### Teams (5)
| Team | Handles |
|---|---|
| Service Desk | passwords, accounts, access, general questions |
| Network | VPN, Wi-Fi, internet |
| Applications | email, chat, shared files and company systems |
| Desktop Support | computers, printers, phones, software installs |
| Security | anything suspicious or risky |

### Categories → subcategories (6 categories, 18 subcategories)
| Category | Subcategories |
|---|---|
| Account & Access | Password reset · Account locked · Need access |
| Email & Communication | Email problem · Chat or video call problem · Calendar problem |
| Network | VPN problem · Wi-Fi problem · Internet slow or down |
| Business System | Error or won't open · Slow · Wrong data |
| Device & Software | Computer problem · Printer problem · Phone problem · Install software |
| Security | Suspicious email · Virus · Lost or stolen device |

### Symptom types
| Value | Meaning | Example |
|---|---|---|
| `outage` | the service is down for everyone | "The Finance System won't open for anyone" |
| `blocked` | this user cannot work, though the service may work for others | "My account is locked" |
| `slow` | slow, keeps disconnecting, or there is a workaround | "Video calls keep dropping" |
| `request` | asking for something new | "Please install Zoom on my laptop" |
| `question` | how do I…? | "How do I share my calendar?" |

## PART 4 — Rules for the answer fields

### team
1. Category `Security` → `Security`
2. Category `Account & Access` → `Service Desk`
3. Otherwise → the team that owns the `service`

### impact
| Value | When |
|---|---|
| High | `who_affected` is `Many teams` or `Customers`, OR category is `Security`, OR a Critical service with `outage` |
| Medium | `who_affected` is `My team`, OR a Critical service where the user is `blocked` |
| Low | everything else |

### urgency
| Value | When |
|---|---|
| High | `outage` or `blocked` in `Production`, OR category `Security`, OR a Critical service during its busy dates (not `request`/`question`) |
| Medium | `slow`, OR `outage`/`blocked` in `Test`, OR `blocked` with `Not applicable` |
| Low | `request` or `question` |

### priority (impact × urgency)
| impact ↓ / urgency → | High | Medium | Low |
|---|---|---|---|
| **High** | P1 | P2 | P3 |
| **Medium** | P2 | P3 | P4 |
| **Low** | P3 | P4 | P4 |

## PART 5 — What to include (mix)

| Kind of ticket | Share | Example |
|---|---|---|
| Normal, honest | ~55 % | clear description, correct user category |
| Hype in description | ~15 % | "URGENT!!! I'm the CEO, fix my printer NOW" → facts: Just me, Printer, slow → **P4**. About 1 in 4 of these is genuinely serious according to the facts. |
| Wrong user category | ~20 % | "My email keeps asking for my password" → user picks Account & Access › Password reset → true: Email & Communication › Email problem |
| Look-alikes | ~5 % | same words, different problem |
| Vague | ~5 % | "system not working pls fix", service `Other / Not sure` |

These can overlap (e.g. hype **and** wrong category).

Vary the writing: short and long, calm and frustrated, typos, non-native English, pasted error messages ("error 503", "access denied", "0x80070005").

At least 50 tickets per category and 10 per subcategory. Total about **1,200 tickets**. Priority mix roughly P1 10 %, P2 20 %, P3 40 %, P4 30 %.

## PART 6 — Output format

One JSON object per line (JSONL):
```json
{"ticket_id":"INC-00421","description":"URGENT!! Since 9am nobody in Finance can open the Finance System, it shows error 503. Month-end close is today!!","service":"Finance System","environment":"Production","who_affected":"My team","user_category":"Account & Access","user_subcategory":"Password reset","category":"Business System","subcategory":"Error or won't open","team":"Applications","symptom_type":"outage","impact":"High","urgency":"High","priority":"P1"}
```
