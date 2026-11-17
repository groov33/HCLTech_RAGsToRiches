# Knowledge Base Generation Prompt — ResolveIQ

Copy everything below the line into the AI that will generate the knowledge base.
It uses exactly the same services, teams, categories and symptom types as `DATA_GENERATION_PROMPT.md`, so tickets and articles match.

---

You are writing the **IT knowledge base** for a company help desk. Each article explains **one specific problem**: how to recognise it, why it happens, what the user can try, what IT support does, and when to escalate.

The articles are used in two ways:
1. **KB Assistant:** employees ask questions and get answers from these articles (only `public` steps are shown to them).
2. **Support Assistant:** when a ticket arrives, the system finds the matching article and builds the recommended fix from its steps, citing the article ID.

So every article must be **specific, step-by-step, and written in plain language**. All names and details are fake. Use only the allowed values below.

## PART 1 — Reference lists (same as the ticket data)

### Services (14)
| Service | What it is | Importance | Owner team |
|---|---|---|---|
| Email | sending and receiving work email | Critical | Applications |
| Company Login | the username and password used for everything | Critical | Service Desk |
| VPN | connecting to the office network from home | Critical | Network |
| Finance System | accounts, invoices, month-end closing | Critical | Applications |
| Payroll System | paying salaries | Critical | Applications |
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
Service Desk · Network · Applications · Desktop Support · Security

### Categories → subcategories
| Category | Subcategories |
|---|---|
| Account & Access | Password reset · Account locked · Need access |
| Email & Communication | Email problem · Chat or video call problem · Calendar problem |
| Network | VPN problem · Wi-Fi problem · Internet slow or down |
| Business System | Error or won't open · Slow · Wrong data |
| Device & Software | Computer problem · Printer problem · Phone problem · Install software |
| Security | Suspicious email · Virus · Lost or stolen device |

### Symptom types
`outage` (down for everyone) · `blocked` (this user can't work) · `slow` (slow, unstable, or has a workaround) · `request` (asking for something new) · `question` (how do I…?)

## PART 2 — Article format

Each article is one JSON object with these fields:

| Field | What to write |
|---|---|
| `kb_id` | `KB-001`, `KB-002`, … |
| `title` | one line naming the specific problem, e.g. "VPN connects but shared drives don't open" |
| `category` | from the Category list |
| `subcategory` | from the Subcategory list; must belong to `category` |
| `services` | list of 1–3 services this applies to |
| `symptom_types` | list of the symptom types this article covers |
| `symptoms` | 3–5 sentences **the way a normal employee would describe it** (casual words, not IT words) |
| `error_messages` | exact messages the user might see; may be empty |
| `cause` | 1–2 plain sentences explaining why it happens |
| `self_help_steps` | 0–5 steps **the employee can safely do themselves**; empty if users shouldn't try anything (e.g. Security, system outages) |
| `support_steps` | 3–8 steps **IT support follows**; each step `{"n":1,"do":"…","expected":"…"}` |
| `verify` | how to confirm it is fixed |
| `escalate_to` | team from the Teams list |
| `escalate_when` | when support should escalate (e.g. "steps fail", "more than one user affected", "data may be exposed") |
| `access_level` | `public` (employees can read it) or `internal` (IT staff only) |
| `keywords` | 5–10 extra words or phrases people might search for, including common misspellings |
| `related_articles` | IDs of 0–3 related articles |

Rules:
- `self_help_steps` must never include anything risky: no deleting data, no changing system settings, no admin actions.
- `support_steps` are concrete actions with an expected result, not vague advice ("check settings" is not allowed; "Open the user's account in the admin panel and check if Status = Locked" is).
- Security articles: the first self-help step is always "Don't click anything else, and disconnect from the network if asked", and the article is escalated to `Security`.
- Articles about a whole service being down (`outage`) have no self-help steps, and `escalate_when` mentions "more than one user affected".

## PART 3 — Coverage (make it comprehensive)

1. **Every subcategory gets 2–4 articles**, each about a **different cause** of that problem. For example, *VPN problem*:
   - "VPN says password incorrect after a password change"
   - "VPN connects but shared drives don't open"
   - "VPN keeps disconnecting on home Wi-Fi"
   - "VPN app won't start after a laptop update"
2. **Every service appears in at least 2 articles.**
3. **Include `question` and `request` articles** too, e.g. "How to share your calendar", "How to request access to a shared folder", "How to install approved software".
4. **Include outage articles for Critical services**, e.g. "Finance System down for everyone: what support should check first".
5. **Include look-alike pairs** whose symptoms sound similar but whose causes differ, and make their `symptoms` show the difference clearly:
   - "Email keeps asking for my password" (email profile problem) vs "I forgot my password" (password reset)
   - "Internet slow in the office" (Wi-Fi) vs "Internet slow only on VPN" (VPN)
   - "Can't open the Finance System" (system error) vs "Finance System says access denied" (need access)
6. **Leave these problems deliberately uncovered** (no article), so the assistant must escalate when it sees them:
   - Company Website showing the wrong prices to customers
   - Payroll System paying the wrong amount to one employee
   - Printer printing blank pages only on one specific floor

Target: **about 55 articles**, roughly 60 % `public` and 40 % `internal`.

## PART 4 — Output format

Return a JSON array. Example of one article:

```json
{
  "kb_id": "KB-014",
  "title": "VPN says password incorrect after a password change",
  "category": "Network",
  "subcategory": "VPN problem",
  "services": ["VPN", "Company Login"],
  "symptom_types": ["blocked"],
  "symptoms": [
    "I changed my password this morning and now the VPN won't let me in",
    "VPN keeps saying wrong password but I can log into email fine",
    "Can't connect from home since I reset my password"
  ],
  "error_messages": ["Authentication failed", "Invalid credentials"],
  "cause": "The VPN app still has the old password saved, so it keeps sending the wrong one.",
  "self_help_steps": [
    "Open the VPN app and choose 'Forget saved password'",
    "Sign in again with your new password",
    "Restart your laptop if it still fails"
  ],
  "support_steps": [
    {"n": 1, "do": "Confirm the user's password was changed in the last 24 hours in the admin panel", "expected": "Recent password change shown"},
    {"n": 2, "do": "Check the VPN sign-in log for repeated failed attempts from this user", "expected": "Failures using the old password"},
    {"n": 3, "do": "Unlock the account if the failures locked it", "expected": "Account status = Active"},
    {"n": 4, "do": "Ask the user to clear the saved password and sign in again", "expected": "VPN connects"}
  ],
  "verify": "The user connects to the VPN and can open a shared folder.",
  "escalate_to": "Network",
  "escalate_when": "Steps fail, or several users report the same error at once.",
  "access_level": "public",
  "keywords": ["vpn password", "remote login failed", "cant connect from home", "vpn auth error", "wfh access"],
  "related_articles": ["KB-002", "KB-015"]
}
```
