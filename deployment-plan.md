# Deployment Plan: Multi-Agent Support Desk

How to run, test, publish and (optionally) host the Support Desk. The required deliverable is the GitHub repository plus the demo; hosting is optional.

---

## 1. Deployment Overview

| Mode | Status | Use |
|------|--------|-----|
| Local (Flask dev server) | Tested | Demo recording, evidence generation |
| GitHub + Actions CI | Required | Submission, unit tests on every push |
| Render free web service | Optional, not tested | Public demo link |

## 2. Deployment Goals
- Reproducible with `pip install -r requirements.txt`, no API key
- No secrets or PII in the repository
- CI runs the unit tests on every push
- Optional hosting needs no code change

## 3. Pre-Deployment Checklist

### 3.1 Repository hygiene
- [ ] `.env` is not tracked (`git status` shows no `.env`)
- [ ] `.gitignore` covers `.env`, `venv/`, `__pycache__/`, `logs/`, `*.pyc`
- [ ] `outputs/evidence/` is committed; `outputs/support_log.*` and `.eml` demo files contain only redacted text
- [ ] `requirements.txt` present; `.env.example` has placeholders only

### 3.2 Code prerequisites
- [ ] `python -m unittest discover -s tests -v` passes (17 tests)
- [ ] `python run_eval.py` ends with every check true and `pii_leaks: []`
- [ ] `CORPUS_LAST_CHECKED` updated after verifying the HDFC facts
- [ ] README numbers match `outputs/evidence/summary.json`

### 3.3 External prerequisites
- [ ] The 15 + 3 source URLs in `SOURCES.md` still open
- [ ] Optional: Groq account and key (console.groq.com)

---

## 4. Run Locally

```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                                       # http://localhost:5000
python run_eval.py                                  # regenerates outputs/evidence/*
python -m unittest discover -s tests -v
```

Optional Groq: copy `.env.example` to `.env`, set `GROQ_API_KEY`. Set `USE_LLM=0` to force template mode. These paths were not exercised; test with your key before relying on them.

---

## 5. GitHub Repository Setup

### 5.1 Create and push
Create an empty public repo `multi-agent-support-desk` on GitHub (no README, no .gitignore), then:

```bash
cd support_desk
git init
git add .
git status            # confirm no .env, no venv, no logs
git commit -m "Multi-agent support desk (Milestone 3)"
git branch -M main
git remote add origin https://github.com/<your-user>/multi-agent-support-desk.git
git push -u origin main
```

### 5.2 GitHub Actions CI
`.github/workflows/ci.yml` installs requirements and runs the unit tests on every push and pull request. A green check on the repo page is part of the evidence.

### 5.3 Files to commit
```
*.py, templates/, tests/, data/reviews.csv
outputs/evidence/
requirements.txt, render.yaml, .env.example, .gitignore
README.md, SOURCES.md, architecture.svg
problemStatement.md, implementation-plan.md, deployment-plan.md
.github/workflows/ci.yml
```

---

## 6. Optional: Render Deployment (not tested)

1. Push to GitHub.
2. Render -> **New -> Web Service** -> select the repo. `render.yaml` supplies:

| Setting | Value |
|---------|-------|
| Build command | `pip install -r requirements.txt gunicorn` |
| Start command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120` |
| Workers | **1**, because tickets are held in memory |
| Plan | free |

3. Add `GROQ_API_KEY` in the Render dashboard only if you want the LLM paths.
4. Open the generated `onrender.com` URL; the free tier sleeps when idle, so the first request is slow.

## 7. Environment Variables

| Variable | Required | Notes |
|----------|----------|-------|
| `GROQ_API_KEY` | No | Never commit; set in `.env` locally or in the Render dashboard |
| `GROQ_MODEL` | No | default `llama-3.3-70b-versatile` |
| `USE_LLM` | No | `0` forces templates |
| `CORPUS_LAST_CHECKED` | No | date shown in replies |

## 8. Security and Privacy
- Redaction runs first in `Desk.submit`; raw text is never stored.
- Logs (`logs/desk_log.jsonl`) hold ids, hashes, agent names, codes only, and are git-ignored.
- MCP payloads are re-scanned for PII and refused if any is found.
- Email drafts are `.eml` files with `X-Unsent`; nothing is ever sent.
- Test PAN/phone/OTP values in the docs are dummy data.
- If hosted publicly, anyone can submit text: do not paste real personal data into the hosted demo.

## 9. Post-Deploy Verification
1. Home page loads; chips fill the message box.
2. **clean** chip: three agent cards, cited reply, "Last checked", reviewer passed.
3. **recurring** chip: HOLD banner, approve button reads "Approve escalation (ticket stays open)".
4. **pii** chip: removed types shown, stored message shows `[PAN REDACTED]`.
5. **advice 1** chip: refusal; refine with a rephrased ask still refuses.
6. Refine "shorter": only orchestrator + reviewer fired.
7. Approve: `outputs/support_log.md` and an `.eml` draft appear.
8. CI badge/check is green on GitHub.

## 10. Rollback Plan
- GitHub: `git revert <commit>` and push; CI re-runs.
- Render: Dashboard -> Deploys -> select an earlier deploy -> Rollback.
- Local data: `outputs/` and `logs/` are generated; deleting them is safe, `python run_eval.py` recreates evidence.

## 11. Monitoring and Maintenance
- Re-run `python run_eval.py` after any change to `corpus_registry.py`, `pii.py`, agents or reviewer, and commit the refreshed evidence.
- Re-verify corpus facts and source URLs periodically and update `CORPUS_LAST_CHECKED`.
- Review `logs/desk_log.jsonl` for `FAIL` / `flagged` rates.

## 12. Cost Considerations
Local and GitHub are free. Render free tier is free with sleep on idle. Groq usage is optional and billed per its own plan; default mode makes no API calls.

## 13. Quick Reference
```bash
python app.py                                   # run
python run_eval.py                              # evidence
python -m unittest discover -s tests -v         # tests
git add . && git commit -m "msg" && git push    # publish (triggers CI)
```

## 14. Related Documents
[problemStatement.md](./problemStatement.md) · [implementation-plan.md](./implementation-plan.md) · [README.md](./README.md) · [SOURCES.md](./SOURCES.md)
