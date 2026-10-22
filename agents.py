"""The three specialist agents. Each takes only the (already redacted) message and returns a
structured dict. None of them reads another agent's output; they run in parallel (see desk.py).

  FactsAgent       -> retrieves one cited fact from the Milestone 1 corpus, or "not covered"
  PatternAgent     -> matches the complaint to Milestone 2 themes, returns trend + count + window
  ComplianceAgent  -> scans the incoming message and (later) the outgoing draft
"""
from __future__ import annotations

import re
import threading

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

import config
import pii
import pipeline  # Milestone 2: load_reviews, cluster_reviews, THEME_LEXICON, FEE_TYPES
from corpus import detect_intents, detect_schemes, get_corpus

# =============================================================================== Facts
class FactsAgent:
    name = "facts"

    def run(self, message: str, scheme_override: str | None = None) -> dict:
        res = get_corpus().search(message, scheme_override=scheme_override)
        return {"agent": self.name, **res}


# =============================================================================== Pattern
class PatternAgent:
    name = "pattern"
    _lock = threading.Lock()
    _idx: dict | None = None

    @classmethod
    def _index(cls) -> dict:
        with cls._lock:
            if cls._idx is None:
                df, info = pipeline.load_reviews(config.REVIEWS_CSV, weeks=12)
                df, themes = pipeline.cluster_reviews(df)           # same themes as Milestone 2
                label = {t["cluster"]: t["label"] for t in themes}
                vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2,
                                      stop_words=pipeline._STOP)
                X = vec.fit_transform(df["text"])
                dfreq = np.asarray((X > 0).sum(axis=0)).ravel()
                inf = dfreq <= 0.05 * X.shape[0]                    # "informative" terms: in <=5% of reviews
                Xb = (X[:, inf] > 0).astype(np.int32)
                cls._idx = {"df": df, "themes": themes, "label": label, "vec": vec, "X": X,
                            "inf": inf, "Xb": Xb, "anchor": df["date"].max()}
            return cls._idx

    def run(self, message: str, window_days: int | None = None, split_days: int | None = None,
            focus: str | None = None) -> dict:
        ix = self._index()
        df, vec, X = ix["df"], ix["vec"], ix["X"]
        window_days = window_days or config.PATTERN_WINDOW_DAYS
        split_days = split_days or config.PATTERN_SPLIT_DAYS
        end = ix["anchor"]
        start = end - pd.Timedelta(days=window_days)
        mid = end - pd.Timedelta(days=split_days)
        in_win = ((df["date"] > start) & (df["date"] <= end)).to_numpy()

        qv = vec.transform([message])
        sims = (X @ qv.T).toarray().ravel() if qv.nnz else np.zeros(len(df))

        # theme: (a) weighted vote of the 15 nearest reviews -> Milestone 2 cluster
        cluster_label, theme_conf, c = None, 0.0, None
        if qv.nnz and sims.max() > 0:
            top = np.argsort(sims)[::-1][:15]
            votes: dict[int, float] = {}
            for i in top:
                votes[int(df["cluster"].iat[i])] = votes.get(int(df["cluster"].iat[i]), 0) + float(sims[i])
            c = max(votes, key=votes.get)
            cluster_label, theme_conf = ix["label"][c], round(votes[c] / max(sum(votes.values()), 1e-9), 2)
        # (b) Milestone 2 lexicon: the words that NAME each theme. The complaint's own words win when they
        # name a theme clearly (M2 clusters are unsupervised and some are mixed); else fall back to (a).
        low = message.lower()
        hits = {lab: len(re.findall(rx, low)) for lab, rx in pipeline.THEME_LEXICON.items()}
        best_lab = max(hits, key=hits.get)
        if hits[best_lab] > 0:
            theme_label, theme_source = best_lab, "M2 theme lexicon"
            lab2c = {v: k for k, v in ix["label"].items()}
            c = lab2c.get(best_lab, c)
        else:
            theme_label, theme_source = cluster_label, "nearest-review cluster vote"

        # "same issue" reviews
        if focus == "fee":
            rx = "|".join(f"(?:{r})" for r in pipeline.FEE_TYPES.values())
            match = df["text"].str.lower().str.contains(rx, regex=True).to_numpy().copy()
            basis = "fee/charge keyword match (pipeline.FEE_TYPES) among 1-3 star reviews"
        else:
            # same issue = similar wording AND at least 2 shared informative (rare) terms, or very high similarity
            qb = (qv[:, ix["inf"]] > 0).astype(np.int32)
            overlap = (ix["Xb"] @ qb.T).toarray().ravel() if qv.nnz else np.zeros(len(df))
            match = (sims >= config.SIM_THRESHOLD) & ((overlap >= 2) | (sims >= 0.35))
            basis = (f"TF-IDF cosine >= {config.SIM_THRESHOLD} plus >=2 shared specific terms, "
                     "among 1-3 star reviews")
        if focus != "fee":
            match = match & (sims < 0.999)                         # never count the input itself
        match = match & (df["rating"] <= 3).to_numpy()             # a "pattern" = other customers who complained (1-3 stars)
        sel = match & in_win
        recent = int((sel & (df["date"] > mid).to_numpy()).sum())
        prior = int((sel & (df["date"] <= mid).to_numpy()).sum())
        total = recent + prior

        if total < config.MIN_RECURRING:
            trend = "one-off"
        elif recent >= config.RISING_RATIO * max(prior, 1) and recent >= config.MIN_RECURRING:
            trend = "rising"
        else:
            trend = "recurring"

        theme_total = int(((df["cluster"] == c).to_numpy() & in_win).sum()) if c is not None else 0
        return {
            "agent": self.name, "trend": trend, "similar_count": total,
            "recent_count": recent, "prior_count": prior,
            "window": {"start": start.date().isoformat(), "end": end.date().isoformat(),
                       "days": window_days, "recent_days": split_days},
            "theme": theme_label, "theme_source": theme_source, "cluster_theme": cluster_label, "theme_confidence": theme_conf, "theme_reviews_in_window": theme_total,
            "basis": basis, "reviews_indexed": int(len(df)),
        }


# =============================================================================== Compliance
ADVICE_REQUEST = [
    r"\bshould (?:i|we)\b",
    r"\b(?:is|are|was)\b[^.?!]{0,45}\b(?:good|bad|safe|worth|better|best|risky|right)\b[^.?!]{0,30}\b(?:fund|scheme|invest\w*|sip|elss|etf|option|choice)\b",
    r"\bwhich\b[^.?!]{0,35}\b(?:fund|scheme)\b[^.?!]{0,25}\b(?:best|better|good|invest|choose|pick|buy)\b",
    r"\b(?:recommend|suggest|advise|advice|opinion)\b",
    r"\b(?:expect\w*|guarantee\w*|assured)\b[^.?!]{0,25}\breturns?\b|\breturns?\b[^.?!]{0,30}\b(?:expect|get|give|make|earn|will|next)\b",
    r"\bhow much\b[^.?!]{0,15}\b(?:will|would|can|could)\b[^.?!]{0,10}\b(?:i|we|it)\b[^.?!]{0,10}\b(?:earn|get|make|gain|grow)\b",
    r"\b(?:good|right|best|wise) time to (?:buy|sell|invest|redeem|exit|switch)\b",
    r"\b(?:buy|sell|redeem|exit|hold|switch|withdraw)\b[^.?!]{0,20}\b(?:or hold|or sell|or not|or stay|or wait)\b",
    r"\bworth (?:it|investing|buying|holding)\b",
    r"\bwill i (?:make|lose|earn|gain)\b",
    r"\b(?:redeem|invest|switch|exit)\b[^.?!]{0,12}\b(?:now|today)\b[^.?!]{0,3}\?",
    r"\bchahiye\b|\bkaru\b|\bkarun\b|\bkaroon\b",
    r"\b(?:would|will|do|did|can|could|shall) you\b[^.?!]{0,30}\b(?:buy|sell|redeem|invest|hold|switch|pick|choose|exit|stay|go for|recommend)\b",
    r"\bif you were (?:me|in my)\b|\bwhat would you do\b|\bwhat do you think\b",
    r"\b(?:yes or no|yes/no)\b",
    r"\bwhether (?:to|i should|we should)\b[^.?!]{0,30}\b(?:buy|sell|redeem|invest|hold|switch|stay|exit|withdraw)\b",
    r"\bstay(?:ing)? invested\b|\bgood time\b",
    r"\b(?:your|the) (?:opinion|view|take|thoughts?)\b",
    r"\b(?:better|best|right|safest|top) (?:for me|option|one|fund|scheme|choice|pick)\b",
    r"\b(?:i want|i need|give me|tell me)\b[^.?!]{0,20}\b(?:the best|a good|a safe|a high|best)\b",
    r"\b(?:convince|persuade) me\b|\bhelp me (?:decide|choose|pick|select)\b",
    r"\brank\b[^.?!]{0,25}\b(?:funds?|schemes?)\b|\bbest to worst\b|\btop (?:[2-9]|10|three|five|ten) funds?\b",
    r"\bshould (?:i|we|my|our|he|she|they|one)\b",
    r"\bregret\b|\byour (?:pick|favou?rite|choice|top)\b",
    r"\b(?:become|be worth|grow to|turn into|double)\b[^.?!]{0,25}\b(?:in|after|by)\b[^.?!]{0,4}\d+ (?:years?|months?|yrs?)",
]
ADVICE_DRAFT = [
    r"\byou (?:should|must|ought to|need to|may want to|might want to|could consider|can consider|would be better)\b",
    r"\b(?:i|we) (?:would |strongly )?(?:recommend|suggest|advise|urge)\b",
    r"\b(?:consider|try) (?:staying|investing|redeeming|holding|switching|buying|selling|exiting|waiting)\b",
    r"\bstay(?:ing)? invested\b",
    r"\b(?:good|great|best|ideal|smart|safe|solid|right|wise|better|safer) (?:fund|scheme|investment|choice|option|pick|time to)\b",
    r"\bworth (?:investing|buying|holding|it)\b",
    r"\b(?:buy|sell|redeem|switch|exit|invest|hold) (?:now|more|again|soon|today|immediately|it|this fund)\b",
    r"\bwill (?:grow|rise|appreciate|outperform|perform|give|deliver|earn|do well)\b",
]
RETURN_CLAIM = [
    r"\b\d+(?:\.\d+)?\s?%\s*(?:p\.?a\.?|per annum|annual\w*|returns?|cagr|growth|gains?|xirr)\b",
    r"\b(?:returns?|cagr|xirr|yield|gains?)\b[^.]{0,30}\d+(?:\.\d+)?\s?%",
    r"\b(?:outperform\w*|underperform\w*|beat (?:the )?(?:market|benchmark)|high returns?|good returns?|guaranteed|assured returns?)\b",
    r"\b(?:1|3|5|7|10)[- ]?(?:year|yr)s? (?:returns?|performance|cagr)\b",
    r"\bpast performance\b",
]


def _hits(patterns: list[str], text: str, kind: str) -> list[dict]:
    out = []
    for rx in patterns:
        if re.search(rx, text, re.I):
            out.append({"category": kind, "rule": rx[:60]})   # the rule, never the matched text
    return out


class ComplianceAgent:
    name = "compliance"

    def run(self, message: str, gate_findings: list[dict] | None = None) -> dict:
        """Scan the incoming (already redacted) message. `gate_findings` are the PII types the
        input gate removed before anything was stored."""
        advice = _hits(ADVICE_REQUEST, message, "advice_request")
        if not advice and config.USE_LLM:                      # optional second opinion for unusual phrasings
            try:
                import llm
                if llm.is_advice_request(message):
                    advice = [{"category": "advice_request", "rule": "llm-intent"}]
            except Exception:                                  # noqa: BLE001
                pass
        # Conservative gate: a fund/scheme question that is NOT a recognised factual question
        # (expense ratio, exit load, SIP minimum, statements, charges...) is treated as advice-seeking.
        if not advice:
            topic = bool(detect_schemes(message)) or bool(re.search(
                r"\b(?:mutual funds?|funds?|schemes?|elss|sips?|etf|nfo|units|redeem\w*|savings|money|portfolio|holdings?)\b", message, re.I))
            qword = bool(re.match(r"\s*(?:is|are|isn't|am|can|could|should|would|will|do|does|which|what|where|who|how|tell|give|suggest|any|between|planning|if)\b", message, re.I))
            qshort = "?" in message and len(message.split()) <= 14
            factual = bool(set(detect_intents(message)) - {"regulator"})
            technical = bool(re.search(r"\b(?:app|crash\w*|login|otp|payment|upi|bank|update|slow|error|bug|server|loading|withdraw\w*)\b", message, re.I))
            descriptive = bool(re.match(r"\s*(?:what|who|where|when|how many|how long|does|do)\b(?! you\b)", message, re.I))
            soft = re.search(r"\b(?:safe|safest|safer|wise|smart|idea|risky|volatile|appropriate|suits?|better than|highest|double my|make money|protect|keep\b[^.?!]{0,25}\b(?:in|invested)|put\b[^.?!]{0,25}\b(?:in|into)|good money)\b", message, re.I)
            if topic and (qword or qshort) and (soft or not (factual or descriptive or technical)):
                advice = [{"category": "advice_request", "rule": "fund question that is not a recognised factual question"}]
        residual = pii.detect(message)
        requested = []
        if advice:
            requested.append("investment_advice")
            if re.search(r"\breturns?\b|\bhow much\b.*\b(?:earn|make|get)\b|\bwill i (?:make|lose)\b", message, re.I):
                requested.append("return_expectation")
        return {
            "agent": self.name,
            "pii_found": gate_findings or [],
            "pii_residual": residual,
            "advice_requested": bool(advice),
            "advice_request_types": requested,
            "return_claim_requested": "return_expectation" in requested,
            "rules_fired": len(advice),
            "incoming_status": "flagged" if (gate_findings or advice) else "clean",
        }

    def scan_draft(self, draft_text: str) -> dict:
        """Second duty: scan the outgoing draft (called by the reviewer after the orchestrator)."""
        advice = _hits(ADVICE_DRAFT, draft_text, "advice_language")
        returns = _hits(RETURN_CLAIM, draft_text, "return_claim")
        return {"advice_language": advice, "return_claims": returns, "pii": pii.detect(draft_text)}


# =============================================================================== schemas
SCHEMAS = {
    "facts": {"agent": str, "status": str, "answer": (str, type(None)), "citation_url": (str, type(None)),
              "searched": list},
    "pattern": {"agent": str, "trend": str, "similar_count": int, "recent_count": int, "prior_count": int,
                "window": dict, "theme": (str, type(None)), "basis": str},
    "compliance": {"agent": str, "pii_found": list, "advice_requested": bool, "incoming_status": str},
}


def validate_output(name: str, out: dict) -> list[str]:
    """Return a list of schema problems (empty = structured output is valid)."""
    problems = []
    for key, typ in SCHEMAS[name].items():
        if key not in out:
            problems.append(f"{name}: missing '{key}'")
        elif not isinstance(out[key], typ):
            problems.append(f"{name}: '{key}' has wrong type {type(out[key]).__name__}")
    if name == "facts" and not problems:
        if out["status"] not in ("covered", "not_covered"):
            problems.append("facts: bad status")
        if out["status"] == "covered" and not (out["answer"] and out["citation_url"]):
            problems.append("facts: covered without answer+citation")
        if out["status"] == "not_covered" and not out["searched"]:
            problems.append("facts: not_covered must name what it searched")
    if name == "pattern" and not problems and out["trend"] not in ("recurring", "rising", "one-off"):
        problems.append("pattern: bad trend")
    return problems
