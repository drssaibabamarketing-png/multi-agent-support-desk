# Branch tests

## 1. Corpus answers cleanly
- **Input (as stored):** What is the lock-in period of HDFC ELSS Tax Saver Fund?
- **PII removed at the gate:** none
- **Agents fired:** facts + pattern + compliance + orchestrator + reviewer (concurrent threads; start spread 4.833 ms, wall 23.33 ms)
- **Facts:** covered -> https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct
- **Pattern:** one-off, 1 similar reviews in 28 days (0 recent / 1 prior), theme 'Mutual funds & SIP'
- **Compliance:** clean; advice asked: False
- **Reviewer attempts:** #1 pass
- **Reply:** "For the HDFC ELSS Tax Saver Fund, the lock-in period is 3 years ([source](https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct)). If this doesn't resolve your concern, reply here and our team will take a look.\n\nLast checked: 22 Oct 2026"
- **Routing note:** Route to: Mutual Funds Desk. Priority: P3 (Low). Facts clean and no escalation signal. Facts: clean answer from https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct. Pattern: one-off - 1 similar reviews in the last 28 days (0 in the last 14 days vs 1 in the 14 days before), 2026-09-23 to 2026-10-21; theme 'Mutual funds & SIP'. Compliance: clean. Action: Send after approval; ticket can close once the customer confirms.

## 2. Corpus cannot answer
- **Input (as stored):** Do HDFC funds invest in cryptocurrency?
- **PII removed at the gate:** none
- **Agents fired:** facts + pattern + compliance + orchestrator + reviewer (concurrent threads; start spread 4.521 ms, wall 25.55 ms)
- **Facts:** not_covered (searched: 74 corpus facts; AMC / AMFI / SEBI page; Groww fee explainer (M2); HDFC scheme page; topics tried: no recognised scheme/fee topic; schemes detected: none)
- **Pattern:** one-off, 1 similar reviews in 28 days (1 recent / 0 prior), theme 'Mutual funds & SIP'
- **Compliance:** clean; advice asked: False
- **Reviewer attempts:** #1 pass
- **Reply:** "I couldn't find this in our official sources, so I've passed it to our team to look into. If this doesn't resolve your concern, reply here and our team will take a look.\n\nLast checked: 22 Oct 2026"
- **Routing note:** Route to: Mutual Funds Desk. Priority: P3 (Low). No cited fact available. Facts: NOT covered by the corpus (searched: HDFC scheme page; topics tried: no recognised scheme/fee topic; schemes detected: none). Pattern: one-off - 1 similar reviews in the last 28 days (1 in the last 14 days vs 0 in the 14 days before), 2026-09-23 to 2026-10-21; theme 'Mutual funds & SIP'. Compliance: clean. Action: OPEN: needs a human answer (corpus does not cover this).

## 3. Matches a recurring theme
- **Input (as stored):** Why is Groww charging so much brokerage and hidden charges on every order?
- **PII removed at the gate:** none
- **Agents fired:** facts + pattern + compliance + orchestrator + reviewer (concurrent threads; start spread 3.446 ms, wall 21.72 ms)
- **Facts:** covered -> https://groww.in/pricing
- **Pattern:** rising, 13 similar reviews in 28 days (9 recent / 4 prior), theme 'Pricing & charges confusion'
- **Compliance:** clean; advice asked: False
- **Reviewer attempts:** #1 pass
- **Reply:** "Brokerage is the fee the broker charges for each executed equity order; Groww publishes its current rates on its pricing page ([source](https://groww.in/pricing)). If this doesn't resolve your concern, reply here and our team will take a look.\n\nLast checked: 22 Oct 2026"
- **Routing note:** Route to: Billing & Charges Support. Priority: P1 (High). Agents disagree: Facts has a clean answer but Pattern shows the same issue is rising (9 in the last 14 days). Facts: clean answer from https://groww.in/pricing. Pattern: rising - 13 similar reviews in the last 28 days (9 in the last 14 days vs 4 in the 14 days before), 2026-09-23 to 2026-10-21; theme 'Pricing & charges confusion'. Compliance: clean. Action: HOLD: do not send as a final answer and do not close the ticket; escalate to the team above.

## 4. Contains a PAN, phone and OTP
- **Input (as stored):** My PAN is [PAN REDACTED] and my phone is [PHONE REDACTED], [OTP REDACTED]. Why was I charged an exit load on HDFC Small Cap Fund?
- **PII removed at the gate:** OTP x1, PAN x1, PHONE x1
- **Agents fired:** facts + pattern + compliance + orchestrator + reviewer (concurrent threads; start spread 5.238 ms, wall 22.58 ms)
- **Facts:** covered -> https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct
- **Pattern:** one-off, 1 similar reviews in 28 days (1 recent / 0 prior), theme 'Pricing & charges confusion'
- **Compliance:** flagged; advice asked: False
- **Reviewer attempts:** #1 pass
- **Reply:** "For the HDFC Small Cap Fund, exit load is 1% if redeemed within 1 year ([source](https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct)). For your security, please don't share PAN, phone numbers or OTPs here; we've removed them from your message.\n\nLast checked: 22 Oct 2026"
- **Routing note:** Route to: Mutual Funds Desk. Priority: P3 (Low). Facts clean and no escalation signal. Facts: clean answer from https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct. Pattern: one-off - 1 similar reviews in the last 28 days (1 in the last 14 days vs 0 in the 14 days before), 2026-09-23 to 2026-10-21; theme 'Pricing & charges confusion'. Compliance: PII removed before storage (OTP, PAN, PHONE). Action: Send after approval; ticket can close once the customer confirms.

### 4b. Reviewer catches PII if an agent echoes it (fault injection)
The orchestrator is replaced by one that copies the customer's raw PAN and phone into the draft. (Values are dummy test data.)

- Attempt 1: **FAIL** - [('UNGROUNDED_FIGURE', '2 figure(s) in the reply do not appear in the retrieved fact'), ('PII_SURVIVED', 'PII still present in the draft or routing note: ACCOUNT, PAN, PHONE')]
- Rework: used; attempt 2: **pass**
- Final reply shown to the human: "For the HDFC Small Cap Fund, exit load is 1% if redeemed within 1 year ([source](https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct)). For your security, please don't share PAN, phone numbers or OTPs here; we've removed them from your message.\n\nLast checked: 22 Oct 2026"

### 4c. Second attempt also fails -> flagged and the send is not offered
Both orchestrator drafts give advice ("You should stay invested longer").

- Attempt 1: ['UNCITED_FACT', 'ADVICE_LANGUAGE']
- Attempt 2 (after the one rework round): ['UNCITED_FACT', 'ADVICE_LANGUAGE']
- flagged = True, send_blocked = True

### 4d. Uncited / ungrounded claim
- Attempt 1 failures: ['UNCITED_FACT', 'UNGROUNDED_FIGURE']; after rework: pass

