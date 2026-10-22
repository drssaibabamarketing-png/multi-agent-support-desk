# Batch run: 20 real complaints from the reviews CSV

Selection: fixed seed; 1-2 star reviews, 60-300 chars; 8 fee/charge complaints + 12 others.

- All three agents returned structured output: **20/20**
- Reply carries a citation or says the corpus doesn't cover it: **20/20**
- Facts covered / not covered: 8 / 12
- Pattern trends: {'recurring': 6, 'one-off': 11, 'rising': 3}
- Orchestrator HOLD (Facts clean but Pattern recurring/rising): 2
- Reviewer pass on first or second draft: 20/20; rework rounds used: 0
- Complaints containing PII (removed at the gate): 0
- Agents fired (all complaints): {'facts': 20, 'pattern': 20, 'compliance': 20, 'orchestrator': 20, 'reviewer': 20}
- Largest start spread between the 3 parallel agents: 11.841 ms

| id | facts | trend (similar) | theme | team | prio | reply check | reviewer |
|---|---|---|---|---|---|---|---|
| R1497 | covered | recurring (8) | Pricing & charges confusion | Billing & Charges Support | P2 | cited | pass |
| R3596 | covered | one-off (4) | Mutual funds & SIP | Billing & Charges Support | P3 | cited | pass |
| R484 | not_covered | recurring (6) | Customer support & trust | Escalations (Customer Experience) | P2 | says not covered | pass |
| R4447 | covered | recurring (8) | Customer support & trust | Billing & Charges Support | P2 | cited | pass |
| R3896 | not_covered | one-off (4) | Order execution & trading reliability | Trading Support | P3 | says not covered | pass |
| R5474 | not_covered | recurring (6) | Customer support & trust | Escalations (Customer Experience) | P2 | says not covered | pass |
| R4437 | not_covered | recurring (7) | Customer support & trust | Escalations (Customer Experience) | P2 | says not covered | pass |
| R1438 | not_covered | rising (6) | Customer support & trust | Escalations (Customer Experience) | P1 | says not covered | pass |
| R3885 | not_covered | one-off (2) | App performance & bugs | App Tech Support | P3 | says not covered | pass |
| R1547 | covered | rising (13) | Pricing & charges confusion | Billing & Charges Support | P1 HOLD | cited | pass |
| R2774 | not_covered | one-off (1) | Pricing & charges confusion | Billing & Charges Support | P3 | says not covered | pass |
| R3031 | covered | rising (8) | Pricing & charges confusion | Billing & Charges Support | P1 HOLD | cited | pass |
| R3343 | not_covered | one-off (1) | Withdrawals, KYC & account issues | Operations & KYC | P3 | says not covered | pass |
| R3154 | covered | recurring (8) | Pricing & charges confusion | Billing & Charges Support | P2 | cited | pass |
| R3277 | covered | one-off (1) | Pricing & charges confusion | Billing & Charges Support | P3 | cited | pass |
| R6149 | covered | one-off (2) | Pricing & charges confusion | Billing & Charges Support | P3 | cited | pass |
| R4422 | not_covered | one-off (2) | App performance & bugs | App Tech Support | P3 | says not covered | pass |
| R4371 | not_covered | one-off (0) | Withdrawals, KYC & account issues | Operations & KYC | P3 | says not covered | pass |
| R1719 | not_covered | one-off (3) | App performance & bugs | App Tech Support | P3 | says not covered | pass |
| R3335 | not_covered | one-off (1) | App performance & bugs | App Tech Support | P3 | says not covered | pass |
