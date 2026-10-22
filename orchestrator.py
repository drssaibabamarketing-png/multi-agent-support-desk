"""Orchestrator: merges Facts + Pattern + Compliance into (1) a reply draft and (2) a routing note.

The reply is built from fixed templates around ONE retrieved fact, so it cannot add claims of its own.
With a Groq key the model may rephrase it; the reviewer then checks the result like any other draft.
"""
from __future__ import annotations

import re

import config
import llm

BOILER = {
    "refusal": "I can't advise on whether to invest or redeem, or on what returns to expect; I can only share facts from official sources.",
    "not_covered": "I couldn't find this in our official sources, so I've passed it to our team to look into.",
    "pii": "For your security, please don't share PAN, phone numbers or OTPs here; we've removed them from your message.",
    "closing": "If this doesn't resolve your concern, reply here and our team will take a look.",
}
BOILER_TEXTS = set(BOILER.values())

TEAM_BY_THEME = {
    "Pricing & charges confusion": "Billing & Charges Support",
    "Order execution & trading reliability": "Trading Support",
    "App performance & bugs": "App Tech Support",
    "Customer support & trust": "Escalations (Customer Experience)",
    "Withdrawals, KYC & account issues": "Operations & KYC",
    "Mutual funds & SIP": "Mutual Funds Desk",
    "Ease of use & positive experience": "Customer Experience (feedback)",
}
PRIORITY = {"rising": ("P1", "High"), "recurring": ("P2", "Medium"), "one-off": ("P3", "Low")}


def _link(url: str) -> str:
    return f"([source]({url}))"


def _routing(facts: dict, pattern: dict, comp: dict, hold: bool, shorter: bool) -> dict:
    # team: the fact's domain wins, then the Pattern theme
    team = TEAM_BY_THEME.get(pattern.get("theme") or "", "General Support")
    if facts["status"] == "covered":
        sid = facts.get("scheme_id", "")
        if sid.startswith("hdfc"):
            team = "Mutual Funds Desk"
        elif sid == "groww_fees":
            team = "Billing & Charges Support"
    if facts.get("schemes_detected"):
        team = "Mutual Funds Desk"
    if comp.get("advice_requested"):
        team = "Mutual Funds Desk (cc: Compliance)"
    code, label = PRIORITY[pattern["trend"]]
    if hold:
        code, label = "P1", "High"
    w = pattern["window"]
    pat = (f"Pattern: {pattern['trend']} - {pattern['similar_count']} similar reviews in the last {w['days']} days "
           f"({pattern['recent_count']} in the last {w['recent_days']} days vs {pattern['prior_count']} in the "
           f"{w['recent_days']} days before), {w['start']} to {w['end']}; theme '{pattern['theme']}'.")
    if facts["status"] == "covered":
        fct = f"Facts: clean answer from {facts['citation_url']}."
    else:
        fct = ("Facts: NOT covered by the corpus (searched: " + "; ".join(facts["searched"][-3:]) + ")."
               + (" Scheme not specified." if facts.get("needs_scheme") else ""))
    flags = []
    if comp.get("pii_found"):
        flags.append("PII removed before storage (" + ", ".join(f['type'] for f in comp['pii_found']) + ")")
    if comp.get("advice_requested"):
        flags.append("customer asked for advice/returns: refusal template used")
    cmp_line = "Compliance: " + ("; ".join(flags) if flags else "clean") + "."
    if hold:
        action = "HOLD: do not send as a final answer and do not close the ticket; escalate to the team above."
        why = (f"Agents disagree: Facts has a clean answer but Pattern shows the same issue is {pattern['trend']} "
               f"({pattern['recent_count']} in the last {w['recent_days']} days).")
    elif facts["status"] != "covered" and comp.get("advice_requested"):
        action = "Send the refusal after approval; do not give advice. No corpus fact applies."
        why = "Advice/returns request: refused by template, nothing factual to add."
    elif facts["status"] != "covered":
        action = "OPEN: needs a human answer (corpus does not cover this)."
        why = "No cited fact available."
    else:
        action = "Send after approval; ticket can close once the customer confirms."
        why = "Facts clean and no escalation signal."
    note = f"Route to: {team}. Priority: {code} ({label}). {why} {fct} {pat} {cmp_line} Action: {action}"
    return {"team": team, "priority": code, "priority_label": label, "ticket_action": action,
            "hold": hold, "reason": why, "note": note}


def run(facts: dict, pattern: dict, comp: dict, *, shorter: bool = False, strict: bool = False,
        rework: list[str] | None = None) -> dict:
    covered = facts["status"] == "covered"
    hold = covered and (pattern["trend"] == "rising" or
                        (pattern["trend"] == "recurring" and pattern["recent_count"] >= config.HOT_RECENT))

    sents: list[dict] = []
    mode = "template"
    llm_sents = None
    if config.USE_LLM and not strict:
        try:
            llm_sents = llm.write_reply(facts["answer"] if covered else None, comp["advice_requested"],
                                        bool(comp["pii_found"]), rework or [])
            mode = "llm"
        except Exception:                                  # noqa: BLE001  fall back to templates
            llm_sents = None

    if comp["advice_requested"]:
        sents.append({"text": BOILER["refusal"], "type": "boilerplate"})
    if llm_sents:
        for s in llm_sents:
            s = s.replace("{LINK}", _link(facts["citation_url"]) if covered else "").replace(" .", ".")
            sents.append({"text": s, "type": "fact" if covered else "boilerplate"})
        sents = sents[:config.MAX_SENTENCES]
    elif covered:
        fact = facts["answer"].rstrip(".")
        sents.append({"text": f"{fact} {_link(facts['citation_url'])}.", "type": "fact"})
    elif not comp["advice_requested"]:
        sents.append({"text": BOILER["not_covered"], "type": "boilerplate"})

    if comp["pii_found"] and not shorter:
        sents.append({"text": BOILER["pii"], "type": "boilerplate"})
    if not shorter and not comp["advice_requested"] and len(sents) < config.MAX_SENTENCES and not comp["pii_found"]:
        sents.append({"text": BOILER["closing"], "type": "boilerplate"})
    sents = sents[:config.MAX_SENTENCES]

    body = " ".join(s["text"] for s in sents)
    footer = f"Last checked: {config.CORPUS_LAST_CHECKED}"
    return {
        "reply": {"sentences": sents, "body": body, "footer": footer, "full_text": f"{body}\n\n{footer}",
                  "citation_url": facts.get("citation_url"), "last_checked": config.CORPUS_LAST_CHECKED},
        "routing": _routing(facts, pattern, comp, hold, shorter),
        "disagreement": hold, "mode": mode, "rework_applied": rework or [],
    }
