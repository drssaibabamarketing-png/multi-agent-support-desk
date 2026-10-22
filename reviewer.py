"""Reviewer: hard-fail checks on a draft before a human ever sees it.

Hard fails: uncited factual claim, advice language, return/performance claim, surviving PII,
figure not found in the retrieved fact, wrong citation, >3 sentences, missing 'last checked'.
Failures carry a code and a PII-free detail so the orchestrator can be told exactly what to fix.
"""
from __future__ import annotations

import re

import config
import llm
from agents import ComplianceAgent
from corpus import ALLOWED_URLS
from orchestrator import BOILER_TEXTS

_LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_DATE = re.compile(r"Last checked:\s*(\d{1,2} [A-Za-z]{3} \d{4})")


def split_reply(full_text: str) -> tuple[list[dict], str | None]:
    """Parse a draft into sentences (each with its citation URLs) and the 'last checked' date."""
    m = _DATE.search(full_text)
    body = full_text[: m.start()].strip() if m else full_text.strip()
    urls: list[str] = []

    def stash(mo):
        urls.append(mo.group(1))
        return f"§{len(urls) - 1}§"

    flat = _LINK.sub(stash, body)
    parts = [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", flat) if p.strip()]
    sents = []
    for p in parts:
        ids = [int(i) for i in re.findall(r"§(\d+)§", p)]
        sents.append({"text": re.sub(r"\(§\d+§\)", "", p).replace("§", "").strip(), "urls": [urls[i] for i in ids]})
    return sents, (m.group(1) if m else None)


def review(orch: dict, facts: dict, comp_agent: ComplianceAgent | None = None) -> dict:
    comp_agent = comp_agent or ComplianceAgent()
    full = orch["reply"]["full_text"]
    note = orch["routing"]["note"]
    sents, last = split_reply(full)
    fails: list[dict] = []

    def fail(code: str, detail: str):
        fails.append({"code": code, "detail": detail})

    # 1. length and last-checked
    if len(sents) > config.MAX_SENTENCES:
        fail("SENTENCE_LIMIT", f"{len(sents)} sentences; the limit is {config.MAX_SENTENCES}")
    if not last:
        fail("MISSING_LAST_CHECKED", "reply has no 'Last checked: <date>' line")

    # 2. citations: every non-boilerplate sentence needs exactly one allowed link; and it must be Facts' link
    covered = facts["status"] == "covered"
    for i, s in enumerate(sents, 1):
        if s["text"] in BOILER_TEXTS or re.sub(r"\s+", " ", s["text"]) in BOILER_TEXTS:
            continue
        if len(s["urls"]) != 1:
            fail("UNCITED_FACT", f"sentence {i} makes a claim but carries {len(s['urls'])} citation links (needs exactly 1)")
        else:
            u = s["urls"][0]
            if u not in ALLOWED_URLS:
                fail("WRONG_CITATION", f"sentence {i} cites a URL outside the corpus source list")
            elif covered and u != facts["citation_url"]:
                fail("WRONG_CITATION", f"sentence {i} cites a different page than the retrieved fact")
        if not covered:
            fail("UNCITED_FACT", f"sentence {i} states something but the corpus did not cover this question")

    # 3. figures must come from the retrieved fact
    plain = _LINK.sub("", " ".join(s["text"] for s in sents))
    allowed_nums = set(_NUM.findall(facts.get("answer") or ""))
    extra = [n for n in _NUM.findall(plain) if n not in allowed_nums]
    if extra:
        fail("UNGROUNDED_FIGURE", f"{len(extra)} figure(s) in the reply do not appear in the retrieved fact")

    # 4. advice language / return claims / PII (draft AND internal note)
    scan = comp_agent.scan_draft(full)
    if scan["advice_language"]:
        fail("ADVICE_LANGUAGE", f"{len(scan['advice_language'])} advice-style phrase(s); the reply must be facts-only")
    if scan["return_claims"]:
        fail("RETURN_CLAIM", f"{len(scan['return_claims'])} return/performance claim(s); remove them")
    leaked = sorted(set(scan["pii"]) | set(comp_agent.scan_draft(note)["pii"]))
    if leaked:
        fail("PII_SURVIVED", "PII still present in the draft or routing note: " + ", ".join(leaked))

    # 5. optional LLM second opinion (only when a key is configured)
    judged = None
    if config.USE_LLM and not fails:
        try:
            judged = llm.judge_advice(full)
            if judged:
                fail("ADVICE_LANGUAGE", "LLM judge flagged advice or return language")
        except Exception:                                  # noqa: BLE001
            judged = None

    return {"passed": not fails, "failures": fails, "sentences": len(sents), "llm_judged": judged}
