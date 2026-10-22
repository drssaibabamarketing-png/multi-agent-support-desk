"""Milestone 1 corpus -> sentence-level, citable chunks, plus retrieval.

Sources: CORPUS_REGISTRY (HDFC scheme pages, statements/KYC pages, AMFI/SEBI) and the Groww fee
knowledge base from Milestone 2 (pipeline.FEE_KB). Every chunk carries exactly one source URL, and
every URL is checked against ALLOWED_URLS (the Milestone 1 source list + Milestone 2 SOURCES.md).

Retrieval is local TF-IDF + intent/scheme matching (no network, no API key, reproducible).
It can be swapped for the Chroma/MiniLM index from Milestone 1 behind `Corpus.search`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import pipeline  # Milestone 2 (FEE_KB)
from corpus_registry import CORPUS_REGISTRY, SCHEMES

# ----------------------------------------------------------------------------- allowed sources
M1_SOURCES = [
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-mid-cap-opportunities-fund/direct",
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct",
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-gold-etf-fund-fund/direct",
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct",
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct",
    "https://www.hdfcfund.com/statutory-disclosure/nav-and-idcw",
    "https://www.hdfcfund.com/investor-services/download-statements/account-statement",
    "https://www.hdfcfund.com/investor-services/download-statements/capital-gains-statement",
    "https://www.hdfcfund.com/investor-services/kyc",
    "https://www.hdfcfund.com/about-us/corporate-governance",
    "https://www.hdfcfund.com/investor-services/downloads/forms",
    "https://www.amfiindia.com/",
    "https://investor.sebi.gov.in/",
    "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doFaq=yes",
    "https://www.sebi.gov.in/legal/master-circulars/may-2023/master-circular-for-mutual-funds_71438.html",
]
M2_SOURCES = [
    "https://groww.in/pricing",
    "https://groww.in/help",
    "https://www.amfiindia.com/investor-corner",
]
ALLOWED_URLS = set(M1_SOURCES + M2_SOURCES)

# corpus_registry.py uses a few URLs that differ from the published M1 source list.
# Citations always use the published list, so map them here (flagged in the README).
URL_FIX = {
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-mid-cap-opportunities-fund": M1_SOURCES[0],
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund": M1_SOURCES[1],
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund": M1_SOURCES[4],
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-gold-etf-fund-fund": M1_SOURCES[2],
    "https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund": M1_SOURCES[3],
    "https://www.hdfcfund.com/nav-and-idcw": M1_SOURCES[5],
    "https://www.hdfcfund.com/services/additional-info/request-statement": M1_SOURCES[6],
    "https://www.hdfcfund.com/services/consolidated-account-statement": M1_SOURCES[7],
    "https://www.hdfcfund.com/services/kyc-redressal-complaints": M1_SOURCES[8],
    "https://www.hdfcfund.com/about-us/corporate-governance/codes-policies": M1_SOURCES[9],
    "https://www.hdfcfund.com/services/forms": M1_SOURCES[10],
}

# Not served as facts: volatile numbers (NAV, AUM) are hand-set in the registry and change daily.
SKIP_SOURCES = {M1_SOURCES[5]}
SKIP_SENTENCE = re.compile(r"\bAUM\b|\bNAV\b|Our board", re.I)

# ----------------------------------------------------------------------------- intents / schemes
INTENTS = {
    "expense_ratio": r"expense ratio|\bter\b|expense",
    "exit_load": r"exit load|redeem|redemption",
    "min_sip": r"minimum sip|sip amount|minimum invest|min(?:imum)? (?:amount|sip)|how much (?:to|can i) invest",
    "riskometer": r"riskometer|risk classification|risk level|how risky",
    "benchmark": r"benchmark",
    "fund_manager": r"fund manager|who manages|managed by|who (?:is|are) the managers?",
    "objective": r"investment objective|objective of",
    "lock_in": r"lock[- ]?in",
    "statement": r"account statement|download.{0,15}statement|folio statement|\bcas\b",
    "capital_gains": r"capital gains?",
    "kyc": r"\bkyc\b",
    "forms": r"\bforms?\b|mandate|redemption request",
    "brokerage": r"brokerage|brokrage|broker charge|trade charges?|\bcharges?\b|charged|\bfees?\b|deduct",
    "dp_charges": r"\bdp\b|depository|demat charge",
    "square_off": r"square.?off|closing charge",
    "regulator": r"\bsebi\b|regulat",
}
SCHEME_SPECIFIC = {"expense_ratio", "exit_load", "min_sip", "riskometer", "benchmark",
                   "fund_manager", "objective", "lock_in"}
SCHEME_ALIASES = {
    "hdfc_small_cap": r"small[- ]?cap",
    "hdfc_mid_cap": r"mid[- ]?cap",
    "hdfc_large_cap": r"large[- ]?cap|top ?100",
    "hdfc_elss": r"\belss\b|tax[- ]?saver|80c",
    "hdfc_gold_etf": r"gold",
}
INTENT_LABEL = {
    "expense_ratio": "expense ratio", "exit_load": "exit load", "min_sip": "minimum SIP",
    "riskometer": "riskometer", "benchmark": "benchmark", "fund_manager": "fund manager",
    "objective": "investment objective", "lock_in": "lock-in", "statement": "account statement",
    "capital_gains": "capital gains statement", "kyc": "KYC", "forms": "forms",
    "brokerage": "Groww charges", "dp_charges": "DP charges", "square_off": "auto square-off",
    "regulator": "regulator",
}

_SPLIT = re.compile(r"(?<=[A-Za-z0-9%\)])\.\s+(?=[A-Z])")


@dataclass
class Chunk:
    id: str
    text: str
    url: str
    scheme_id: str
    source: str                         # human label, e.g. "HDFC scheme page"
    intents: list[str] = field(default_factory=list)
    prior: float = 0.0
    group: str = ""


def detect_intents(text: str) -> list[str]:
    t = (text or "").lower()
    return [k for k, rx in INTENTS.items() if re.search(rx, t)]


def detect_schemes(text: str) -> list[str]:
    t = (text or "").lower()
    return [k for k, rx in SCHEME_ALIASES.items() if re.search(rx, t)]


def _sentences(content: str) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(content) if p.strip()]
    return [p if p.endswith((".", "?", "!")) else p + "." for p in parts]


def _build() -> list[Chunk]:
    chunks: list[Chunk] = []
    # --- Milestone 1 registry
    for i, item in enumerate(CORPUS_REGISTRY):
        url = URL_FIX.get(item["url"], item["url"])
        if url in SKIP_SOURCES:
            continue
        assert url in ALLOWED_URLS, f"registry URL not in the published source list: {url}"
        scheme_id = item["scheme_id"]
        name = SCHEMES.get(scheme_id, "")
        label = "HDFC scheme page" if item["source_type"] == "primary" else "AMC / AMFI / SEBI page"
        sents = _sentences(item["content"])
        for j, s in enumerate(sents):
            if SKIP_SENTENCE.search(s):
                continue
            if scheme_id != "general" and j == 0:       # title sentence, e.g. "HDFC Small Cap Fund Direct Growth."
                continue
            s = re.sub(r"^.*?\?\s+", "", s)             # drop a leading FAQ question
            if scheme_id != "general":
                s = f"For the {name}, {s[0].lower() + s[1:]}"
            ch = Chunk(f"reg{i}-{j}", s, url, scheme_id, label)
            ch.intents = detect_intents(s)
            chunks.append(ch)
    # --- Milestone 2 Groww fee knowledge base
    for fee, kb in pipeline.FEE_KB.items():
        url = kb["sources"][0][1]
        assert url in ALLOWED_URLS
        for j, b in enumerate(kb["bullets"]):
            ch = Chunk(f"fee-{fee[:6]}-{j}", b, url, "groww_fees", "Groww fee explainer (M2)")
            ch.intents = detect_intents(b + " " + fee)
            ch.prior = 0.25 if j == 0 else 0.0
            ch.group = fee          # the opening definition is the default answer for a topic
            chunks.append(ch)
    return chunks


class Corpus:
    def __init__(self) -> None:
        self.chunks = _build()
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.X = self.vec.fit_transform([c.text for c in self.chunks])
        self.sources_searched = sorted({c.source for c in self.chunks})

    def describe(self) -> str:
        n_urls = len({c.url for c in self.chunks})
        return f"{len(self.chunks)} facts from {n_urls} public pages ({', '.join(self.sources_searched)})"

    def search(self, query: str, scheme_override: str | None = None) -> dict:
        """Return the best chunk or a 'not covered' result naming what was searched."""
        intents = detect_intents(query)
        schemes = [scheme_override] if scheme_override else detect_schemes(query)
        qv = self.vec.transform([query])
        sims = cosine_similarity(qv, self.X).ravel()

        def pick(pool: list[int]) -> int | None:
            return max(pool, key=lambda i: sims[i] + self.chunks[i].prior) if pool else None

        idx_all = list(range(len(self.chunks)))
        best = None
        # 1) scheme-specific facts for a named scheme
        spec = [i for i in intents if i in SCHEME_SPECIFIC]
        if schemes and spec:
            pool = [i for i in idx_all if self.chunks[i].scheme_id in schemes
                    and set(self.chunks[i].intents) & set(spec)]
            best = pick(pool)
        # 2) intent facts from general pages (statements, KYC, forms, Groww fees, SEBI/AMFI)
        if best is None and intents:
            wanted = set(intents)
            pool = [i for i in idx_all if set(self.chunks[i].intents) & wanted
                    and self.chunks[i].scheme_id in ("general", "groww_fees")]
            # prefer Groww fee wording when the complaint is about brokerage/charges
            if pool and wanted & {"brokerage", "dp_charges", "square_off"} and not (wanted & SCHEME_SPECIFIC):
                fee_pool = [i for i in pool if self.chunks[i].scheme_id == "groww_fees"]
                if not (wanted & {"dp_charges", "square_off"}):       # plain "charges/brokerage" -> brokerage topic
                    fee_pool = [i for i in fee_pool if self.chunks[i].group.startswith("Brokerage")] or fee_pool
                pool = fee_pool or pool
            best = pick(pool)
            if best is not None and sims[best] < 0.05 and not (wanted & {"statement", "capital_gains", "kyc", "forms", "brokerage", "dp_charges", "square_off"}):
                best = None
        # 3) pure similarity fallback, but only with a strong match
        if best is None:
            # strip scheme/product words first so a scheme name alone can never "match" a fact
            core = re.sub(r"small[- ]?cap|mid[- ]?cap|large[- ]?cap|top ?100|\belss\b|tax[- ]?saver|gold|hdfc|"
                          r"\bfunds?\b|schemes?|mutual|groww|\bunits?\b", " ", query, flags=re.I)
            sims2 = cosine_similarity(self.vec.transform([core]), self.X).ravel()
            i = int(sims2.argmax())
            if sims2[i] >= 0.35:
                best = i
                sims = sims2
        if best is None:
            what = [INTENT_LABEL[i] for i in intents] or ["no recognised scheme/fee topic"]
            needs_scheme = bool([i for i in intents if i in SCHEME_SPECIFIC]) and not schemes
            return {
                "status": "not_covered", "answer": None, "citation_url": None,
                "searched": [f"{len(self.chunks)} corpus facts", *self.sources_searched,
                             f"topics tried: {', '.join(what)}",
                             f"schemes detected: {', '.join(SCHEMES[s] for s in schemes) or 'none'}"],
                "needs_scheme": needs_scheme, "schemes_detected": schemes,
            }
        c = self.chunks[best]
        return {
            "status": "covered", "answer": c.text, "citation_url": c.url,
            "chunk_id": c.id, "scheme_id": c.scheme_id, "source_label": c.source, "score": round(float(sims[best]), 3),
            "intents": intents, "schemes_detected": schemes,
            "searched": [f"{len(self.chunks)} corpus facts", *self.sources_searched],
        }


_CORPUS: Corpus | None = None


def get_corpus() -> Corpus:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = Corpus()
    return _CORPUS
