"""python -m unittest discover -s tests -v   (run from the project root)"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import eval_set
import mcp_layer as mcp
import orchestrator as orch_mod
import pii
import reviewer
from agents import ComplianceAgent, FactsAgent, PatternAgent, validate_output
from desk import Desk

DESK = Desk()
CLEAN = eval_set.BRANCH_INPUTS["clean"]


def bad_orch(make_body, always=False):
    def fn(facts, pattern, comp, **kw):
        good = orch_mod.run(facts, pattern, comp, **kw)
        if always or not kw.get("strict"):
            d = copy.deepcopy(good)
            body = make_body(good)
            d["reply"]["body"], d["reply"]["full_text"] = body, f"{body}\n\n{d['reply']['footer']}"
            return d
        return good
    return fn


class PiiTests(unittest.TestCase):
    def test_all_types_redacted(self):
        raw = ("PAN ABCDE1234F phone 9876543210 mail a.b@x.com aadhaar 1234 5678 9012 "
               "account number 123456789012 OTP 482913")
        out, found = pii.redact(raw)
        self.assertEqual(pii.detect(out), [])
        self.assertTrue({"PAN", "PHONE", "EMAIL", "AADHAAR", "ACCOUNT", "OTP"} <= {f["type"] for f in found})
        for v in ("ABCDE1234F", "9876543210", "a.b@x.com", "482913"):
            self.assertNotIn(v, out)


class AgentTests(unittest.TestCase):
    def test_structured_outputs(self):
        for m in (CLEAN, eval_set.BRANCH_INPUTS["not_covered"], "my app crashes"):
            t = DESK.submit(m)
            self.assertEqual(t["schema_problems"], [])
            for n in ("facts", "pattern", "compliance"):
                self.assertEqual(validate_output(n, t["outputs"][n]), [])

    def test_not_covered_names_what_was_searched_and_no_general_knowledge(self):
        f = FactsAgent().run("Do HDFC funds invest in cryptocurrency?")
        self.assertEqual(f["status"], "not_covered")
        self.assertIsNone(f["answer"])
        self.assertTrue(f["searched"])

    def test_agents_run_in_parallel(self):
        t = DESK.submit(CLEAN)
        self.assertTrue(t["timing"]["parallel"])
        self.assertEqual(set(t["timing"]["agents"]), {"facts", "pattern", "compliance"})
        self.assertLess(t["timing"]["start_spread_ms"], 100)

    def test_compliance_scans_draft(self):
        c = ComplianceAgent()
        self.assertTrue(c.scan_draft("You should stay invested longer.")["advice_language"])
        self.assertTrue(c.scan_draft("This fund gave 18% returns last year.")["return_claims"])
        self.assertFalse(c.scan_draft("The expense ratio is 0.74%.")["return_claims"])


class ReviewerTests(unittest.TestCase):
    def codes(self, body, facts_q=CLEAN):
        t = DESK.submit(facts_q)
        d = copy.deepcopy(t["draft"])
        d["reply"]["body"], d["reply"]["full_text"] = body, f"{body}\n\n{d['reply']['footer']}"
        return {f["code"] for f in reviewer.review(d, t["outputs"]["facts"])["failures"]}

    def test_hard_fails(self):
        self.assertIn("UNCITED_FACT", self.codes("The lock-in period is 3 years."))
        self.assertIn("ADVICE_LANGUAGE", self.codes("You should stay invested for longer."))
        self.assertIn("RETURN_CLAIM", self.codes("It delivered 15% returns last year."))
        self.assertIn("PII_SURVIVED", self.codes("Your PAN ABCDE1234F is noted."))
        self.assertIn("SENTENCE_LIMIT", self.codes("One. Two. Three. Four."))

    def test_missing_last_checked_and_wrong_figure(self):
        t = DESK.submit(CLEAN)
        d = copy.deepcopy(t["draft"])
        d["reply"]["full_text"] = d["reply"]["body"]
        self.assertIn("MISSING_LAST_CHECKED", {f["code"] for f in reviewer.review(d, t["outputs"]["facts"])["failures"]})
        d2 = copy.deepcopy(t["draft"])
        d2["reply"]["body"] = d2["reply"]["body"].replace("3 years", "5 years")
        d2["reply"]["full_text"] = d2["reply"]["body"] + "\n\n" + d2["reply"]["footer"]
        self.assertIn("UNGROUNDED_FIGURE", {f["code"] for f in reviewer.review(d2, t["outputs"]["facts"])["failures"]})

    def test_rework_capped_at_one_and_send_blocked(self):
        d = Desk(orchestrator_fn=bad_orch(lambda g: "You should stay invested. " + g["reply"]["body"], always=True))
        t = d.submit(CLEAN)
        self.assertEqual(len(t["review_attempts"]), 2)
        self.assertTrue(t["flagged"] and t["send_blocked"])

    def test_rework_fixes_the_draft(self):
        d = Desk(orchestrator_fn=bad_orch(lambda g: "You should stay invested. " + g["reply"]["body"]))
        t = d.submit(CLEAN)
        self.assertFalse(t["review_attempts"][0]["passed"])
        self.assertTrue(t["review_attempts"][1]["passed"])
        self.assertFalse(t["flagged"])


class DeskTests(unittest.TestCase):
    def test_every_reply_cited_or_not_covered(self):
        for c in eval_set.sample_complaints(20):
            t = DESK.submit(c["text"])
            body = t["draft"]["reply"]["body"]
            f = t["outputs"]["facts"]
            self.assertTrue((f["status"] == "covered" and f["citation_url"] in body) or
                            (f["status"] != "covered" and orch_mod.BOILER["not_covered"] in body), c["id"])
            self.assertLessEqual(t["review"]["sentences"], 3)
            self.assertIn("Last checked:", t["draft"]["reply"]["full_text"])

    def test_disagreement_holds_ticket(self):
        t = DESK.submit(eval_set.BRANCH_INPUTS["recurring"])
        self.assertEqual(t["outputs"]["facts"]["status"], "covered")
        self.assertIn(t["outputs"]["pattern"]["trend"], ("rising", "recurring"))

    def test_advice_always_refused(self):
        for q in eval_set.ADVICE_ATTACKS + eval_set.ADVICE_REPHRASED:
            t = DESK.submit(q)
            self.assertIn(orch_mod.BOILER["refusal"], t["draft"]["reply"]["body"], q)
            self.assertTrue(t["review"]["passed"])

    def test_refinement_only_affected_agents_and_cap(self):
        t = DESK.submit("Why was I charged an exit load on my HDFC fund?")
        r = DESK.refine(t["tid"], "shorter")
        self.assertEqual(r["agents_fired"], ["orchestrator", "reviewer"])
        r = DESK.refine(t["tid"], "they're asking about the HDFC Mid-Cap fund")
        self.assertEqual(r["agents_fired"], ["facts", "orchestrator", "reviewer"])
        r = DESK.refine(t["tid"], "check if this is the fee issue from last week")
        self.assertEqual(r["agents_fired"], ["pattern", "orchestrator", "reviewer"])
        self.assertEqual((t["counters"]["facts"], t["counters"]["pattern"], t["counters"]["compliance"]), (2, 2, 1))
        DESK.refine(t["tid"], "shorter please")
        DESK.refine(t["tid"], "shorter again")
        self.assertFalse(DESK.refine(t["tid"], "one more")["ok"])
        self.assertEqual(t["refinements_used"], config.MAX_REFINEMENTS)

    def test_no_pii_in_state_or_logs(self):
        t = DESK.submit(eval_set.BRANCH_INPUTS["pii"])
        dump = json.dumps(t, default=str)
        for v in ("ABCDE1234F", "9876543210", "482913"):
            self.assertNotIn(v, dump)
        self.assertEqual(pii.detect(dump), [])
        log = (config.LOGS / "desk_log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(pii.detect(log), [])
        self.assertNotIn("ABCDE1234F", log)


class McpTests(unittest.TestCase):
    def test_gate_blocks_everything_until_human_approves(self):
        t = DESK.submit(CLEAN)
        rec, mail = mcp.build_payloads(t)
        g = mcp.ApprovalGate("x")
        with self.assertRaises(mcp.ApprovalRequired):
            mcp.call_tool("append_support_record", rec, g)
        g.decide(False)
        with self.assertRaises(mcp.ApprovalRequired):
            mcp.call_tool("create_email_draft", mail, g)

    def test_payload_with_pii_refused(self):
        t = DESK.submit(CLEAN)
        rec, _ = mcp.build_payloads(t)
        rec["complaint_redacted"] = "my PAN ABCDE1234F"
        g = mcp.ApprovalGate("x")
        g.decide(True)
        with self.assertRaises(ValueError):
            mcp.call_tool("append_support_record", rec, g)

    def test_flagged_ticket_cannot_be_approved_in_ui(self):
        import app as A
        A.DESK = Desk(orchestrator_fn=bad_orch(lambda g: "You should stay invested. " + g["reply"]["body"], always=True))
        c = A.app.test_client()
        loc = c.post("/submit", data={"message": CLEAN}).headers["Location"]
        r = c.post(loc + "/decide", data={"decision": "approve"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
