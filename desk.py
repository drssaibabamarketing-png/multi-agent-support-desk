"""The Support Response Desk: input gate -> 3 parallel agents -> orchestrator -> reviewer -> human.

State rules enforced here:
  * the raw message is redacted at the very first line of `submit` and never stored or logged
  * the three agents run in parallel threads (a barrier makes them start together) and never see each other's output
  * reviewer rework: max 1 round per draft; refinements: max 5 per ticket; every turn logs which agents fired
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config
import orchestrator as orch_mod
import pii
import reviewer as reviewer_mod
from agents import ComplianceAgent, FactsAgent, PatternAgent, validate_output
from corpus import detect_schemes
from corpus_registry import SCHEMES

LOG = config.LOGS / "desk_log.jsonl"
_log_lock = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(event: dict) -> None:
    """Append-only log. Never receives message text: only ids, hashes, agent names, codes and counts."""
    config.LOGS.mkdir(exist_ok=True)
    with _log_lock, LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), **event}, ensure_ascii=False) + "\n")


class Desk:
    def __init__(self, orchestrator_fn=None) -> None:
        self.tickets: dict[str, dict] = {}
        self.facts, self.pattern, self.compliance = FactsAgent(), PatternAgent(), ComplianceAgent()
        self._orch = orchestrator_fn or orch_mod.run          # injectable for fault-injection tests
        PatternAgent._index()                                  # warm the theme index once

    # ------------------------------------------------------------------ parallel stage
    def _parallel(self, jobs: dict) -> tuple[dict, dict]:
        """Run the given agent callables concurrently. Returns (outputs, timing)."""
        barrier = threading.Barrier(len(jobs))
        t0 = time.perf_counter()
        marks: dict[str, tuple[float, float]] = {}

        def wrap(name, fn):
            def go():
                barrier.wait()                                 # all agents start together
                s = time.perf_counter()
                out = fn()
                marks[name] = (s, time.perf_counter())
                return name, out
            return go

        with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
            futs = [ex.submit(wrap(n, f)) for n, f in jobs.items()]
            outs = dict(f.result() for f in futs)
        t1 = time.perf_counter()
        starts = [m[0] for m in marks.values()]
        timing = {
            "agents": {n: {"start_ms": round((m[0] - t0) * 1000, 2), "duration_ms": round((m[1] - m[0]) * 1000, 2)}
                       for n, m in marks.items()},
            "start_spread_ms": round((max(starts) - min(starts)) * 1000, 3),
            "wall_ms": round((t1 - t0) * 1000, 2),
            "sum_of_agent_ms": round(sum((m[1] - m[0]) for m in marks.values()) * 1000, 2),
            "parallel": len(jobs) > 1,
        }
        return outs, timing

    # ------------------------------------------------------------------ orchestrate + review
    def _draft_and_review(self, t: dict) -> None:
        o = t["outputs"]
        fired = ["orchestrator", "reviewer"]
        attempts = []
        draft = self._orch(o["facts"], o["pattern"], o["compliance"], shorter=t["opts"]["shorter"])
        rv = reviewer_mod.review(draft, o["facts"], self.compliance)
        attempts.append({"attempt": 1, "passed": rv["passed"], "failures": rv["failures"]})
        rework = 0
        if not rv["passed"] and config.MAX_REWORK >= 1:
            rework = 1
            reasons = [f"{f['code']}: {f['detail']}" for f in rv["failures"]]
            draft = self._orch(o["facts"], o["pattern"], o["compliance"], shorter=t["opts"]["shorter"],
                               strict=True, rework=reasons)
            rv = reviewer_mod.review(draft, o["facts"], self.compliance)
            attempts.append({"attempt": 2, "passed": rv["passed"], "failures": rv["failures"]})
            fired += ["orchestrator(rework)", "reviewer(rework)"]
        t["draft"], t["review"] = draft, rv
        t["review_attempts"] = attempts
        t["rework_used"] = rework
        t["flagged"] = not rv["passed"]                        # still failing after the one rework round
        t["send_blocked"] = t["flagged"]
        t["counters"]["orchestrator"] += 1 + rework
        t["counters"]["reviewer"] += 1 + rework
        return fired

    # ------------------------------------------------------------------ public API
    def submit(self, raw_message: str, session_id: str = "default") -> dict:
        message, gate_findings = pii.redact(raw_message)       # FIRST: raw text goes no further than this line
        del raw_message
        tid = secrets.token_hex(4)
        t = {
            "tid": tid, "session": session_id, "created": _now(), "message": message,
            "pii_removed": gate_findings, "outputs": {}, "timing": {}, "opts": {"shorter": False},
            "overrides": {"scheme": None, "pattern": {}}, "advice_sticky": False,
            "counters": {k: 0 for k in ("facts", "pattern", "compliance", "orchestrator", "reviewer")},
            "refinements_used": 0, "refine_log": [], "fired_log": [], "decision": "pending",
        }
        jobs = {
            "facts": lambda: self.facts.run(message),
            "pattern": lambda: self.pattern.run(message),
            "compliance": lambda: self.compliance.run(message, gate_findings),
        }
        outs, timing = self._parallel(jobs)
        t["outputs"], t["timing"] = outs, timing
        for n in jobs:
            t["counters"][n] += 1
        t["schema_problems"] = [p for n in jobs for p in validate_output(n, outs[n])]
        fired = ["facts", "pattern", "compliance"] + self._draft_and_review(t)
        t["fired_log"].append({"turn": 0, "what": "initial run", "agents_fired": fired})
        self.tickets[tid] = t
        self._log(t, "submit", fired)
        return t

    def refine(self, tid: str, instruction: str) -> dict:
        t = self.tickets[tid]
        if t["refinements_used"] >= config.MAX_REFINEMENTS:
            return {"ok": False, "error": f"Refinement cap reached ({config.MAX_REFINEMENTS}). Start a new ticket."}
        instr, _ = pii.redact(instruction)
        plan = self._plan(instr)
        if plan.get("clarify"):
            return {"ok": False, "clarify": plan["clarify"], "error": plan["clarify"]}

        o, fired = t["outputs"], []
        jobs = {}
        if "facts" in plan["agents"]:
            if plan.get("scheme"):
                t["overrides"]["scheme"] = plan["scheme"]
            sch = t["overrides"]["scheme"]
            jobs["facts"] = lambda: self.facts.run(t["message"], scheme_override=sch)
        if "pattern" in plan["agents"]:
            t["overrides"]["pattern"].update(plan.get("pattern_opts", {}))
            po = dict(t["overrides"]["pattern"])
            jobs["pattern"] = lambda: self.pattern.run(t["message"], **po)
        if "compliance" in plan["agents"]:
            both = t["message"] + " " + instr
            jobs["compliance"] = lambda: self.compliance.run(both, t["pii_removed"])
        if jobs:
            outs, timing = self._parallel(jobs)
            for n, out in outs.items():
                o[n] = out
                t["counters"][n] += 1
            t["timing"] = timing
            fired += list(jobs)
        # advice asked at any point in the session sticks for this ticket (refusal cannot be talked out of)
        if self.compliance.run(instr)["advice_requested"]:
            if not t["advice_sticky"]:
                fired.append("compliance")                     # the scan changed state, so it is logged as fired
            t["advice_sticky"] = True
        if t["advice_sticky"]:
            o["compliance"] = {**o["compliance"], "advice_requested": True,
                               "advice_request_types": sorted(set(o["compliance"].get("advice_request_types", []) + ["investment_advice"]))}
        if plan.get("shorter"):
            t["opts"]["shorter"] = True
        fired += self._draft_and_review(t)
        t["refinements_used"] += 1
        turn = t["refinements_used"]
        t["refine_log"].append({"turn": turn, "instruction": instr, "agents_fired": fired})
        t["fired_log"].append({"turn": turn, "what": instr, "agents_fired": fired})
        self._log(t, "refine", fired, turn=turn)
        return {"ok": True, "agents_fired": fired}

    # ------------------------------------------------------------------ refinement router
    @staticmethod
    def _plan(instr: str) -> dict:
        s = instr.lower()
        agents: list[str] = []
        plan: dict = {}
        named = detect_schemes(s)
        diff_scheme = re.search(r"different (?:scheme|fund)|another (?:scheme|fund)|wrong (?:scheme|fund)|other (?:scheme|fund)", s)
        if named or diff_scheme:
            if not named:
                plan["clarify"] = ("Which scheme is the customer asking about? Say e.g. 'it's about HDFC Mid-Cap' "
                                   "(small cap, mid cap, large cap/Top 100, ELSS, gold). Nothing was re-run.")
                return plan
            agents.append("facts")
            plan["scheme"] = named[0]
        if re.search(r"pattern|recurr|rising|trend|last week|this week|last month|same issue|fee issue|known issue|"
                     r"other users|how many|check if this is|is this common", s):
            agents.append("pattern")
            opts = {}
            if re.search(r"last week|this week", s):
                opts.update(window_days=14, split_days=7)
            elif re.search(r"last month", s):
                opts.update(window_days=56, split_days=28)
            if re.search(r"fee|charge|brokerage", s):
                opts["focus"] = "fee"
            plan["pattern_opts"] = opts
        if re.search(r"shorter|shorten|brief|concise|too long|trim", s):
            plan["shorter"] = True
        if re.search(r"compliance|advice|pii|redact|personal data|sensitive|make sure it.?s safe", s):
            agents.append("compliance")
        plan["agents"] = agents
        return plan

    # ------------------------------------------------------------------ logging
    def _log(self, t: dict, event: str, fired: list[str], **extra) -> None:
        o = t["outputs"]
        log_event({
            "event": event, "ticket": t["tid"], "session": t["session"],
            "msg_hash": hashlib.sha256(t["message"].encode()).hexdigest()[:10],
            "agents_fired": fired,
            "facts": o["facts"]["status"], "pattern": o["pattern"]["trend"],
            "pii_types_removed": [f["type"] for f in t["pii_removed"]],
            "reviewer": "pass" if t["review"]["passed"] else "FAIL",
            "failure_codes": [f["code"] for f in t["review"]["failures"]],
            "rework_used": t["rework_used"], "flagged": t["flagged"], **extra,
        })


def scheme_name(sid: str | None) -> str:
    return SCHEMES.get(sid or "", "")
