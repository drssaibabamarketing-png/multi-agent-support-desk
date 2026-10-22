"""Deterministic PII detection and redaction (PAN, Aadhaar, account/folio numbers, phone, email, OTP).

Used at the input gate (before anything is stored), by the Compliance agent, by the
Reviewer on every outgoing draft, and by the MCP layer as a last check.
Only TYPES and COUNTS are ever reported, never the matched value.
"""
from __future__ import annotations

import re

# Order matters: more specific patterns first so a number is labelled once.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("OTP", re.compile(r"(?i)\b(?:otp|one[- ]?time[- ]?(?:password|pin)|verification code|passcode)\b[^\d\n]{0,25}\d{4,8}\b")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("PAN", re.compile(r"\b[A-Za-z]{5}[0-9]{4}[A-Za-z]\b")),
    ("ACCOUNT", re.compile(r"(?i)\b(?:a/c|acct|account|folio|demat|client\s*id|dp\s*id)\b(?:\s*(?:no|number|num|#|id))?[\s:.#-]*\d[\d\s-]{4,20}\d")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("ACCOUNT", re.compile(r"(?<!\d)\d{9,18}(?!\d)")),   # any other long digit run
]


def redact(text: str) -> tuple[str, list[dict]]:
    """Return (redacted_text, findings) where findings = [{'type': 'PAN', 'count': 1}, ...]."""
    counts: dict[str, int] = {}
    out = text or ""
    for label, rx in PATTERNS:
        out, n = rx.subn(f"[{label} REDACTED]", out)
        if n:
            counts[label] = counts.get(label, 0) + n
    return out, [{"type": k, "count": v} for k, v in counts.items()]


def detect(text: str) -> list[str]:
    """Return the PII types still present in `text` (empty list = clean)."""
    found: list[str] = []
    probe = text or ""
    for label, rx in PATTERNS:
        if rx.search(probe) and label not in found:
            found.append(label)
    return found
