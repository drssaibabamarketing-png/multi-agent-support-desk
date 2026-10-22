# Implementation Plan: Multi-Agent Support Desk

Implementation roadmap for the system specified in [problemStatement.md](./problemStatement.md) (NextLeap Gen AI, Milestone 3). Product: **Groww**, with **HDFC Mutual Fund** schemes, as in Milestones 1 and 2.

---

## 1. Summary

| Item | Decision |
|------|----------|
| **Goal** | Turn one customer question or complaint into a facts-only reply draft plus an internal routing note, reviewed before a human sees it |
| **Stack** | Python 3.11, Flask UI, scikit-learn (TF-IDF), pandas |
| **Agents** | Facts, Pattern, Compliance (parallel threads), then Orchestrator, then Reviewer |
| **LLM** | Optional Groq (`llama-3.3-70b-versatile`); default is deterministic templates and rules, so runs are reproducible and need no key |
| **Retrieval** | Local TF-IDF plus intent and scheme matching over sentence-level corpus chunks (Milestone 1 corpus) |
| **Approval** | Milestone 2 `ApprovalGate`; two tools after approval: `append_support_record`, `create_email_draft` (never sent) |
| **Persistence** | Local files only (`outputs/`, `logs/`), no database |
| **Tests** | `unittest` (17 tests) and `run_eval.py` evidence generator |

---

## 2. High-Level Architecture

```
Customer message (typed, or a 1-2 star review from reviews.csv)
        |
        v
  Input gate: pii.redact()   <- raw text goes no further than this line
        |
        +------------------+------------------+
        v                  v                  v
   Facts Agent       Pattern Agent     Compliance Agent      (threads, barrier start,
   M1 corpus,        M2 themes +       PII, advice asked      none reads another)
   1 citation        reviews CSV
        +------------------+------------------+
                           v
                     Orchestrator -> reply (<=3 sentences, 1 link, "Last checked")
                           |         + routing note (team, priority, HOLD)
                           v
                       Reviewer -> hard fails -> 1 rework -> flag, block approve
                           |
                           v
              Human: refine (max 5, affected agents only) / Approve
                           |
                           v
              MCP after approval: append record + email draft (never sent)
```

**Design principles:** redact before anything else, agents see only the redacted message, reply built from one retrieved fact so it cannot add claims, every rule enforced in code and not only in a prompt, logs hold ids/hashes/codes and never message text.

---

## 3. Project Structure

```
support_desk/
├── app.py, templates/            # Flask UI (index, ticket)
├── desk.py                       # input gate, parallel stage, review/rework loop, refinement router, logging
├── agents.py                     # Facts, Pattern, Compliance + output schemas
├── orchestrator.py               # reply + routing note
├── reviewer.py                   # hard-fail checks
├── corpus.py, corpus_registry.py # Milestone 1 corpus, citations, retrieval
├── pipeline.py, data/reviews.csv # Milestone 2 themes and reviews
├── mcp_layer.py                  # ApprovalGate, append_support_record, create_email_draft
├── pii.py, llm.py, config.py     # redaction, optional Groq client, settings
├── eval_set.py, run_eval.py      # inputs and evidence generator
├── tests/test_desk.py
├── outputs/evidence/             # generated evidence
├── .github/workflows/ci.yml
├── .env.example, .gitignore, requirements.txt, render.yaml
├── README.md, SOURCES.md, architecture.svg
└── problemStatement.md, implementation-plan.md, deployment-plan.md
```

---

## 4. Implementation Phases

### Phase 0: Reuse and bootstrap
| # | Task | Details |
|---|------|---------|
| 0.1 | Copy Milestone 1 corpus | `corpus_registry.py`, 15 published source URLs |
| 0.2 | Copy Milestone 2 pipeline | `pipeline.py`, `data/reviews.csv`, `ApprovalGate` from `mcp_layer.py` |
| 0.3 | Settings | `config.py` constants (caps, thresholds, last-checked date) |
| 0.4 | `.env.example`, `.gitignore`, `requirements.txt` | no secrets committed |

**Exit criteria:** `pip install -r requirements.txt` works and old pipeline code imports.

### Phase 1: Input gate (`pii.py`)
Regex redaction for OTP, email, PAN, account number, Aadhaar, phone. Returns the clean text plus findings (type and count only).
**Exit criteria:** a message holding a PAN and phone number comes out as `[PAN REDACTED]`, `[PHONE REDACTED]`; findings never contain the raw value.

### Phase 2: Facts agent (`corpus.py`, `agents.FactsAgent`)
Sentence-level chunks, scheme detection, intent detection (exit load, SIP minimum, riskometer, fund manager, Groww fees), URL whitelist and `URL_FIX`.
**Exit criteria:** covered question returns one fact and one allowed URL; uncovered returns `not_covered` plus what it searched; no general-knowledge fallback.

### Phase 3: Pattern agent (`agents.PatternAgent`)
Theme from the Milestone 2 lexicon first, cluster vote second. Similar reviews: cosine >= 0.15 and >= 2 shared rare terms among 1-3 star reviews. 28-day window split 14/14. Trend: one-off (< 5), recurring, rising (recent >= 1.5x prior and >= 5).
**Exit criteria:** returns trend, similar count, window start/end and theme for every input.

### Phase 4: Compliance agent (`agents.ComplianceAgent`)
Incoming scan (PII types, advice and return requests) and `scan_draft()` for the outgoing draft. Optional LLM intent check on top of the regex rules.
**Exit criteria:** all 23 advice attacks flagged; factual questions and complaints not flagged.

### Phase 5: Parallel stage (`desk._parallel`)
Three threads behind a `threading.Barrier`, each given only the redacted message; timing and start spread recorded for the UI.
**Exit criteria:** start spread in milliseconds shown on the ticket page.

### Phase 6: Orchestrator and reviewer
Templates for refusal, not covered, PII notice and closing. Routing note: team, priority (rising P1, recurring P2, one-off P3), agent findings, action. HOLD when Facts is clean but Pattern is rising, or recurring with 10+ in the last 14 days. Reviewer hard fails: `UNCITED_FACT`, `WRONG_CITATION`, `ADVICE_LANGUAGE`, `RETURN_CLAIM`, `PII_SURVIVED`, `UNGROUNDED_FIGURE`, `SENTENCE_LIMIT`, `MISSING_LAST_CHECKED`. One rework round, then flag and block approve (also a server-side 403).
**Exit criteria:** fault-injected drafts (echoed PAN, uncited claim, invented figure) are caught.

### Phase 7: Refinement router
`Desk._plan` maps an instruction to affected agents only. Cap 5. Advice asked once stays sticky for the ticket. "Different scheme" without a name asks which one and re-runs nothing. Every turn logs which agents fired.

### Phase 8: Approval-gated MCP (`mcp_layer.py`)
`call_tool()` raises unless the gate is approved; payloads re-scanned for PII; audit log. HOLD tickets are recorded as `escalated_open` and the email subject is prefixed `[HOLD - escalate before sending]`.

### Phase 9: UI (`app.py`, `templates/`)
Submit page with branch chips and 20 sampled complaints; ticket page with three agent cards, reply, routing note, reviewer attempts, refine table, approval box.

### Phase 10: Evidence and tests
`run_eval.py` writes batch (20 complaints), branches with fault injection, advice attacks, refinement, gate test and a PII grep over every output file. `tests/test_desk.py` has 17 tests.

### Phase 11: Documentation and submission
README (architecture, rules map, evidence, demo script, limitations), SOURCES.md, these three plan files, push to GitHub, 2-minute demo.

---

## 5. Contracts

### Agent outputs (validated by `agents.validate_output`)
| Agent | Fields |
|-------|--------|
| Facts | `status` (`covered` / `not_covered`), `answer`, `citation_url`, `searched` |
| Pattern | `trend`, `similar_count`, `recent_count`, `prior_count`, `window {days, start, end, recent_days}`, `theme` |
| Compliance | `incoming_status`, `pii_found [{type,count}]`, `advice_requested`, `advice_request_types` |

### Orchestrator output
`reply {sentences, body, footer "Last checked: <date>", full_text, citation_url}`, `routing {team, priority, note, hold}`, `mode`.

### Reviewer output
`passed`, `failures [{code, detail}]`, per-attempt history (max 2 attempts).

---

## 6. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | none | Enables the optional LLM paths |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `USE_LLM` | on if key present | Set `0` to force template mode |
| `CORPUS_LAST_CHECKED` | `22 Oct 2026` | Date printed as "Last checked"; update after re-verifying the corpus |

---

## 7. Dependency List

| Package | Use |
|---------|-----|
| flask | UI |
| pandas, numpy | reviews loading, pipeline |
| scikit-learn, scipy | TF-IDF retrieval and review similarity |
| requests | optional Groq client |
| gunicorn | only for optional Render deploy |

---

## 8. Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Corpus facts are hand-written fallback text, not re-checked against live HDFC pages | Wrong fact in a reply | Verify against the five scheme pages, update `corpus_registry.py` and `CORPUS_LAST_CHECKED` |
| Regex advice detection bypassed by new phrasing | Advice-like request not flagged | Draft-side scan and reviewer still block advice language; optional LLM check |
| Groq paths untested | LLM mode misbehaves | Deterministic fallback; every LLM draft goes through the same reviewer |
| Pattern thresholds tuned on 6 weeks of reviews | Trend labels off | Documented; thresholds in `config.py` |
| PII in logs or outputs | Compliance breach | Redact first, ids/hashes only in logs, payload re-scan, `run_eval.py` greps every output |
| In-memory tickets lost on restart | Lost state | Acceptable for a demo; documented |
| Citation URL changes or dies | Broken link | `ALLOWED_URLS` and `URL_FIX`; recheck sources before submitting |

---

## 9. Acceptance Criteria Checklist

- [ ] 20 real complaints run; all three agents return structured output on each
- [ ] Every reply carries one citation or says the corpus does not cover it
- [ ] Four branches tested (clean, not covered, recurring, PAN/phone); agents fired logged; reviewer catches the PII
- [ ] Advice attacks (asked, rephrased, repeated later, pushed back) refused every time
- [ ] Replies are 3 sentences or fewer with a "last checked" date
- [ ] Reviewer rework capped at 1; flagged draft cannot be approved
- [ ] Refinement capped at 5; only affected agents re-run; fired agents logged
- [ ] Nothing written or drafted until a human approves; email never sent
- [ ] No PII in logs, agent state or outputs (`summary.json` -> `pii_leaks: []`)
- [ ] Parallel execution shown in the diagram, the UI and the demo
- [ ] Public sources only, listed in `SOURCES.md`
- [ ] README, plans, evidence files pushed to GitHub; demo recorded; link submitted

---

## 10. Suggested Implementation Order

1. Phases 0-1 (reuse, input gate)
2. Phases 2-4 (three agents, tested one at a time)
3. Phase 5 (parallel stage)
4. Phase 6 (orchestrator, reviewer)
5. Phases 7-8 (refinement, MCP gate)
6. Phase 9 (UI)
7. Phase 10 (evidence, tests)
8. Phase 11 (docs, GitHub, demo)

---

## 11. Future Enhancements (out of scope)

- Swap the simulated MCP tools for real Google Docs / Gmail MCP calls (the gate does not change)
- Chroma/MiniLM retrieval from Milestone 1 behind `Corpus.search`
- Persist tickets in a database; multi-worker deployment
- Live corpus refresh with automatic "last checked" timestamp
- LLM-based advice classifier as a second line of defence, with its own eval set

---

## 12. References

- [problemStatement.md](./problemStatement.md), the Milestone 3 brief
- [deployment-plan.md](./deployment-plan.md)
- [SOURCES.md](./SOURCES.md), public sources used
- [README.md](./README.md), architecture, evidence and limitations
