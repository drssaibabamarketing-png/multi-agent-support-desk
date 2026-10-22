"""Optional Groq client (OpenAI-compatible endpoint, plain `requests`, no SDK needed).

If GROQ_API_KEY is not set, or a call fails, callers fall back to the deterministic templates,
so the desk always works. The reviewer validates every LLM-written draft exactly like a template draft.
"""
from __future__ import annotations

import json
import time

import requests

import config

URL = "https://api.groq.com/openai/v1/chat/completions"


def chat_json(system: str, user: str, retries: int = 2, timeout: int = 20) -> dict:
    import os
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    body = {
        "model": config.GROQ_MODEL, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(URL, json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 429:                      # free-tier rate limit: back off and retry
                time.sleep(2 * (attempt + 1))
                last = RuntimeError("rate limited")
                continue
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:                            # noqa: BLE001
            last = e
            time.sleep(1)
    raise RuntimeError(f"Groq call failed: {last}")


def write_reply(fact: str | None, advice_requested: bool, pii_removed: bool, failures: list[str]) -> list[str]:
    """Ask the model for <=2 customer-facing sentences. {LINK} marks where the citation goes."""
    system = (
        "You write short customer-support replies for an Indian investing app. Facts-only. "
        "Use ONLY the FACT given. Keep every number exactly as written. Never recommend, never say what "
        "the customer should do with their investments, never mention returns or performance. "
        "If FACT is null, say politely that it is not covered in official sources and that you've passed it "
        "to the team (no other claims). Output JSON: {\"sentences\": [..]} with at most 2 sentences. "
        "Put the literal token {LINK} once, inside the sentence that states the FACT, just before its full stop."
    )
    user = json.dumps({"FACT": fact, "customer_asked_for_advice": advice_requested,
                       "pii_was_removed": pii_removed, "fix_these_problems": failures})
    out = chat_json(system, user)
    sents = [s.strip() for s in out.get("sentences", []) if isinstance(s, str) and s.strip()]
    if not sents:
        raise RuntimeError("empty LLM reply")
    return sents[:2]


def judge_advice(text: str) -> bool:
    """LLM second opinion for subtle advice/return claims the regexes may miss."""
    system = ("You are a compliance checker. Answer JSON {\"violation\": true|false}. violation=true if the text "
              "recommends or nudges any investment action (buy/sell/hold/redeem/switch/stay invested/consider), "
              "judges a scheme as good/bad/safe, or states or implies returns/performance.")
    return bool(chat_json(system, text).get("violation"))


def is_advice_request(text: str) -> bool:
    """LLM second opinion on whether the customer is asking for investment advice or return expectations."""
    system = ("Answer JSON {\"advice\": true|false}. advice=true if the customer asks what they should do with an "
              "investment, whether a scheme is good/bad/safe/worth it, which scheme is better, or what returns to expect.")
    return bool(chat_json(system, text).get("advice"))
