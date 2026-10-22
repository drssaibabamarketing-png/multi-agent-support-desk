# Refinement tests: only the affected agents re-run

- `shorter` -> fired ['orchestrator', 'reviewer'] (expected ['orchestrator', 'reviewer']): **ok**
- `they're asking about the HDFC Mid-Cap fund` -> fired ['facts', 'orchestrator', 'reviewer'] (expected ['facts', 'orchestrator', 'reviewer']): **ok**
- `check if this is the fee issue from last week` -> fired ['pattern', 'orchestrator', 'reviewer'] (expected ['orchestrator', 'pattern', 'reviewer']): **ok**

Run counters after 3 refinements (initial run = 1 each): {'facts': 2, 'pattern': 2, 'compliance': 1, 'orchestrator': 4, 'reviewer': 4}
Facts answer now: For the HDFC Mid Cap Fund, exit load is 1% if redeemed within 1 year.
Pattern now: recurring (27), window 14 days, basis: fee/charge keyword match (pipeline.FEE_TYPES) among 1-3 star reviews

- `they're asking about a different scheme` (no scheme named) -> {'ok': False, 'clarify': "Which scheme is the customer asking about? Say e.g. 'it's about HDFC Mid-Cap' (small cap, mid cap, large cap/Top 100, ELSS, gold). Nothing was re-run.", 'error': "Which scheme is the customer asking about? Say e.g. 'it's about HDFC Mid-Cap' (small cap, mid cap, large cap/Top 100, ELSS, gold). Nothing was re-run."}
- 6th refinement -> {'ok': False, 'error': 'Refinement cap reached (5). Start a new ticket.'}

Log of agents fired per turn: [
 {
  "turn": 0,
  "what": "initial run",
  "agents_fired": [
   "facts",
   "pattern",
   "compliance",
   "orchestrator",
   "reviewer"
  ]
 },
 {
  "turn": 1,
  "what": "shorter",
  "agents_fired": [
   "orchestrator",
   "reviewer"
  ]
 },
 {
  "turn": 2,
  "what": "they're asking about the HDFC Mid-Cap fund",
  "agents_fired": [
   "facts",
   "orchestrator",
   "reviewer"
  ]
 },
 {
  "turn": 3,
  "what": "check if this is the fee issue from last week",
  "agents_fired": [
   "pattern",
   "orchestrator",
   "reviewer"
  ]
 },
 {
  "turn": 4,
  "what": "shorter",
  "agents_fired": [
   "orchestrator",
   "reviewer"
  ]
 },
 {
  "turn": 5,
  "what": "please shorten it again",
  "agents_fired": [
   "orchestrator",
   "reviewer"
  ]
 }
]
