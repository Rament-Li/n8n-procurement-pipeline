import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS = os.path.join(HERE, "..")
sys.path.insert(0, EVALS)
import check_no_secrets  # noqa: E402
import run_evals  # noqa: E402
import scoring  # noqa: E402

CASES = json.load(open(os.path.join(EVALS, "cases.json"), encoding="utf-8"))


class CaseFileTests(unittest.TestCase):
    def test_count_and_unique_ids(self):
        self.assertEqual(len(CASES), 30)
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))

    def test_required_keys(self):
        for c in CASES:
            for key in ("id", "tag", "received", "subject", "from", "body", "expected"):
                self.assertIn(key, c, c.get("id"))
            self.assertTrue(c["body"].strip(), c["id"])
            self.assertRegex(c["received"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(set(c["expected"]) <= set(scoring.FIELDS), c["id"])
            self.assertIn("docType", c["expected"])

    def test_expected_dates_are_iso(self):
        for c in CASES:
            d = c["expected"].get("order_date")
            if d:
                self.assertRegex(d, r"^\d{4}-\d{2}-\d{2}$", c["id"])

    def test_only_fictional_example_addresses(self):
        for c in CASES:
            addresses = re.findall(r"[\w.+-]+@[\w.-]+", c["from"] + c["body"])
            for a in addresses:
                self.assertTrue(a.endswith(".example.com"), c["id"] + " " + a)

    def test_every_doc_type_is_covered(self):
        types = set()
        for c in CASES:
            t = c["expected"]["docType"]
            types.update(t if isinstance(t, list) else [t])
        self.assertTrue({"order", "dispatch", "delivery", "invoice", "other"} <= types)


class PromptTests(unittest.TestCase):
    def test_prompts_exist_and_differ(self):
        d = os.path.join(EVALS, "prompts")
        files = sorted(f for f in os.listdir(d) if f.endswith(".txt"))
        self.assertGreaterEqual(len(files), 2)
        texts = [open(os.path.join(d, f), encoding="utf-8").read() for f in files]
        self.assertEqual(len(set(texts)), len(texts))

    def test_request_layout_matches_workflow(self):
        msg = run_evals.build_user_message("PROMPT", CASES[0])
        self.assertIn("\n\nReceived: " + CASES[0]["received"], msg)
        self.assertIn("\nSubject: " + CASES[0]["subject"], msg)
        self.assertTrue(msg.startswith("PROMPT"))


class SecretSafetyTests(unittest.TestCase):
    def test_scanner_detects_fake_keys(self):
        fake = "sk-" + "ant-" + "a" * 30
        self.assertTrue(check_no_secrets.scan(extra_text="key = " + fake))
        self.assertTrue(check_no_secrets.scan(extra_text="ANTHROPIC_API_KEY=" + "b" * 24))
        self.assertTrue(check_no_secrets.scan(extra_text="-----BEGIN " + "PRIVATE KEY-----"))

    def test_scanner_ignores_normal_text(self):
        self.assertFalse(check_no_secrets.scan(extra_text="export the key from your environment"))

    def test_repository_has_no_credentials(self):
        self.assertEqual(check_no_secrets.scan(), [])

    def test_runner_has_no_key_argument_and_reads_env_only(self):
        source = open(os.path.join(EVALS, "run_evals.py"), encoding="utf-8").read()
        self.assertNotIn("--api-key", source)
        self.assertIn('os.environ.get("ANTHROPIC_API_KEY"', source)
        self.assertNotIn("print(api_key", source)


class OracleTests(unittest.TestCase):
    def test_expected_answers_score_as_correct(self):
        """A model that returns exactly the expected answer must pass every case."""
        for c in CASES:
            out = {}
            for k, v in c["expected"].items():
                if isinstance(v, list) and k == "docType":
                    out[k] = v[0]
                elif isinstance(v, list) and k == "order_ref":
                    out[k] = v[0]
                elif k == "items" and v is not None:
                    out[k] = [{"product": i["product"], "sku": i["sku"], "quantity": str(i["quantity"])} for i in v]
                elif v is not None:
                    out[k] = v
            if c["expected"].get("items") is None:
                out["items"] = []
            self.assertTrue(scoring.score_case(out, c["expected"])["passed"], c["id"])


if __name__ == "__main__":
    unittest.main()
