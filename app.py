"""Flask UI: paste a complaint (or pick one from the reviews CSV) -> three parallel agents ->
orchestrator -> reviewer -> refine (max 5) -> human APPROVE -> MCP actions (append record + email draft)."""
import os
import re

from flask import Flask, abort, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import config
import eval_set
import mcp_layer as mcp
from desk import Desk

app = Flask(__name__)
DESK = Desk()
GATES: dict[str, mcp.ApprovalGate] = {}
DONE: dict[str, list] = {}
SAMPLES = eval_set.sample_complaints()


@app.template_filter("reply_html")
def reply_html(text):
    """Escape, then turn [source](url) into a link."""
    t = str(escape(text))
    t = re.sub(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    return Markup(t.replace("\n", "<br>"))


@app.get("/")
def index():
    return render_template("index.html", samples=SAMPLES, branch=eval_set.BRANCH_INPUTS,
                           attacks=eval_set.ADVICE_ATTACKS, llm=config.USE_LLM)


@app.post("/submit")
def submit():
    msg = (request.form.get("message") or "").strip()
    if not msg:
        return redirect(url_for("index"))
    t = DESK.submit(msg[:2000], session_id=request.remote_addr or "local")   # raw text is redacted inside submit()
    GATES[t["tid"]] = mcp.ApprovalGate("Append record to support log + create email draft (no send)")
    return redirect(url_for("ticket", tid=t["tid"]))


@app.get("/ticket/<tid>")
def ticket(tid):
    t = DESK.tickets.get(tid) or abort(404)
    return render_template("ticket.html", t=t, gate=GATES[tid], done=DONE.get(tid), cfg=config,
                           tools=mcp.list_tools(), left=config.MAX_REFINEMENTS - t["refinements_used"],
                           msg=request.args.get("msg"))


@app.post("/ticket/<tid>/refine")
def refine(tid):
    t = DESK.tickets.get(tid) or abort(404)
    if GATES[tid].status != "pending":
        abort(400, "ticket already decided")
    res = DESK.refine(tid, (request.form.get("instruction") or "")[:500])
    return redirect(url_for("ticket", tid=tid, msg=None if res.get("ok") else res.get("error")))


@app.post("/ticket/<tid>/decide")
def decide(tid):
    t = DESK.tickets.get(tid) or abort(404)
    gate = GATES[tid]
    if gate.status != "pending":
        return redirect(url_for("ticket", tid=tid))
    approve = request.form.get("decision") == "approve"
    if approve and t["send_blocked"]:
        abort(403, "The reviewer flagged this draft; it cannot be approved or sent.")
    gate.decide(approve)                                   # <-- the ONLY place approval is granted
    t["decision"] = gate.status
    if approve:
        record, email = mcp.build_payloads(t)
        DONE[tid] = [("append_support_record", mcp.call_tool("append_support_record", record, gate)),
                     ("create_email_draft", mcp.call_tool("create_email_draft", email, gate))]
    return redirect(url_for("ticket", tid=tid))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
