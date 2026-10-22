"""MCP-style tool layer with the same approval gate as Milestone 2.

NO tool executes unless a human-approved ApprovalGate is passed in. After approval the desk:
  1. append_support_record -> outputs/support_log.md + .jsonl   (stand-in for the Google Doc)
  2. create_email_draft    -> outputs/support_reply_draft.eml   (X-Unsent, NEVER sent)
Swap the two bodies for Google Docs / Gmail MCP calls to go live; the gate does not change.
Defence in depth: every payload is re-scanned for PII and refused if any survives.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from email.message import EmailMessage

import config
import pii

OUT = config.OUT


class ApprovalRequired(PermissionError):
    pass


class ApprovalGate:
    """Created pending; only a human click flips it."""

    def __init__(self, summary: str):
        self.id = secrets.token_hex(4)
        self.summary = summary
        self.status = "pending"          # pending | approved | rejected
        self.decided_at = None

    def decide(self, approve: bool):
        self.status = "approved" if approve else "rejected"
        self.decided_at = datetime.now().isoformat(timespec="seconds")


TOOLS = {
    "append_support_record": {
        "description": "Append the approved ticket record (redacted complaint, reply, citation, routing note) to the team log.",
        "inputSchema": {"type": "object", "required": [
            "ticket_id", "date", "complaint_redacted", "reply_draft", "citation_url", "last_checked",
            "routing_note", "priority", "ticket_status", "agents_fired"]},
    },
    "create_email_draft": {
        "description": "Create an email DRAFT (.eml, X-Unsent). Never sends.",
        "inputSchema": {"type": "object", "required": ["subject", "body"]},
    },
}


def list_tools() -> list[dict]:
    return [{"name": n, **t} for n, t in TOOLS.items()]


def _append_support_record(a: dict) -> dict:
    OUT.mkdir(exist_ok=True)
    md = OUT / "support_log.md"
    entry = (f"\n---\n## Ticket {a['ticket_id']} - {a['date']}  [{a['priority']}]  status: {a['ticket_status']}\n"
             f"**Complaint (redacted):** {a['complaint_redacted']}\n\n"
             f"**Reply draft:**\n\n{a['reply_draft']}\n\n"
             f"**Citation:** {a['citation_url'] or 'none (not covered by corpus)'}  |  **Last checked:** {a['last_checked']}\n\n"
             f"**Routing note:** {a['routing_note']}\n\n"
             f"**Agents fired:** {', '.join(a['agents_fired'])}\n")
    with md.open("a", encoding="utf-8") as f:
        f.write(entry)
    with (OUT / "support_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(a, ensure_ascii=False) + "\n")
    return {"ok": True, "path": md.name, "chars_appended": len(entry)}


def _create_email_draft(a: dict) -> dict:
    OUT.mkdir(exist_ok=True)
    m = EmailMessage()
    m["Subject"] = a["subject"]
    m["To"] = a.get("to", "")            # left blank: customer contact details are never stored
    m["X-Unsent"] = "1"
    m.set_content(a["body"])
    p = OUT / "support_reply_draft.eml"
    p.write_bytes(bytes(m))
    (OUT / "support_reply_draft.txt").write_text(f"Subject: {a['subject']}\n\n{a['body']}", encoding="utf-8")
    return {"ok": True, "path": p.name, "sent": False}


_IMPL = {"append_support_record": _append_support_record, "create_email_draft": _create_email_draft}


def call_tool(name: str, arguments: dict, gate: ApprovalGate) -> dict:
    if gate is None or gate.status != "approved":
        raise ApprovalRequired(f"'{name}' blocked: approval gate is {getattr(gate, 'status', 'missing')}")
    missing = [k for k in TOOLS[name]["inputSchema"]["required"] if k not in arguments]
    if missing:
        raise ValueError(f"missing arguments: {missing}")
    leaked = pii.detect(json.dumps(arguments, ensure_ascii=False))
    if leaked:
        raise ValueError("payload still contains PII (" + ", ".join(leaked) + "); refusing to store it")
    res = _IMPL[name](arguments)
    OUT.mkdir(exist_ok=True)
    with (OUT / "audit_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "tool": name,
                            "gate": gate.id, "approved_at": gate.decided_at, "result": res}) + "\n")
    return res


def build_payloads(t: dict) -> tuple[dict, dict]:
    d = t["draft"]
    hold = d["routing"]["hold"]
    flat_fired = [a for e in t["fired_log"] for a in e["agents_fired"]]
    status = "escalated_open (ticket NOT closed)" if hold else ("open (needs human answer)"
             if t["outputs"]["facts"]["status"] != "covered" else "reply approved")
    record = {
        "ticket_id": t["tid"], "date": datetime.now().date().isoformat(),
        "complaint_redacted": t["message"], "reply_draft": d["reply"]["full_text"],
        "citation_url": d["reply"]["citation_url"], "last_checked": d["reply"]["last_checked"],
        "routing_note": d["routing"]["note"], "priority": d["routing"]["priority"],
        "ticket_status": status, "agents_fired": flat_fired,
        "pii_types_removed": [f["type"] for f in t["pii_removed"]],
    }
    prefix = "[HOLD - escalate before sending] " if hold else ""
    email = {
        "to": "", "subject": f"{prefix}Support reply draft - ticket {t['tid']}",
        "body": f"{d['reply']['full_text']}\n\n--- INTERNAL (remove before sending) ---\n{d['routing']['note']}",
    }
    return record, email
