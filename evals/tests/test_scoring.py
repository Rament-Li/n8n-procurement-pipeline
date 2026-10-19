import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scoring  # noqa: E402

EXP = {"docType": "order", "supplier": "Northgate Lab Supplies", "order_ref": "NG-48213", "status": "Ordered",
       "order_date": "2026-09-03", "currency": "GBP",
       "items": [{"product": "nitrile gloves", "sku": "NG-GLV-M100", "quantity": 5}]}

GOOD = {"docType": "order", "supplier": "Northgate Lab Supplies Ltd", "order_ref": "NG48213", "status": "ordered",
        "order_date": "2026-09-03", "currency": "gbp",
        "items": [{"product": "Nitrile gloves, size M", "sku": "NG-GLV-M100", "quantity": "5"}]}


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(scoring.parse_model_json('{"a": 1}'), {"a": 1})

    def test_code_fences_and_prose(self):
        self.assertEqual(scoring.parse_model_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(scoring.parse_model_json('Here you go: {"a": 1} Thanks'), {"a": 1})

    def test_invalid(self):
        self.assertIsNone(scoring.parse_model_json("not json"))
        self.assertIsNone(scoring.parse_model_json(None))
        self.assertIsNone(scoring.parse_model_json("[1, 2]"))


class ScoreCaseTests(unittest.TestCase):
    def test_all_correct(self):
        r = scoring.score_case(GOOD, EXP)
        self.assertTrue(r["passed"])
        self.assertFalse(r["invalid_json"])

    def test_invalid_json_fails_everything(self):
        r = scoring.score_case(None, EXP)
        self.assertTrue(r["invalid_json"])
        self.assertFalse(r["passed"])
        self.assertTrue(all(v is False for v in r["fields"].values()))

    def test_wrong_order_ref(self):
        bad = dict(GOOD, order_ref="SP123456789GB")
        r = scoring.score_case(bad, EXP)
        self.assertFalse(r["fields"]["order_ref"])
        self.assertFalse(r["passed"])

    def test_accepted_list_for_doctype(self):
        exp = dict(EXP, docType=["other", "order"])
        self.assertTrue(scoring.score_case(dict(GOOD, docType="other"), exp)["fields"]["docType"])
        self.assertFalse(scoring.score_case(dict(GOOD, docType="invoice"), exp)["fields"]["docType"])

    def test_unscored_fields_are_skipped(self):
        exp = dict(EXP, order_date=None, currency=None)
        r = scoring.score_case(dict(GOOD, order_date="1999-01-01", currency="XXX"), exp)
        self.assertNotIn("order_date", r["fields"])
        self.assertTrue(r["passed"])

    def test_empty_expected_reference(self):
        exp = dict(EXP, order_ref="")
        self.assertTrue(scoring.score_case(dict(GOOD, order_ref=""), exp)["fields"]["order_ref"])
        self.assertFalse(scoring.score_case(dict(GOOD, order_ref="NG-1"), exp)["fields"]["order_ref"])


class ItemTests(unittest.TestCase):
    def test_extra_item_fails(self):
        got = GOOD["items"] + [{"product": "Delivery", "sku": "", "quantity": "1"}]
        self.assertFalse(scoring.score_items(got, EXP["items"]))

    def test_missing_item_fails(self):
        self.assertFalse(scoring.score_items([], EXP["items"]))

    def test_wrong_quantity_fails(self):
        got = [dict(GOOD["items"][0], quantity="6")]
        self.assertFalse(scoring.score_items(got, EXP["items"]))

    def test_name_match_when_sku_missing(self):
        got = [{"product": "Nitrile gloves size M", "sku": "", "quantity": 5}]
        self.assertTrue(scoring.score_items(got, EXP["items"]))

    def test_empty_expected_list(self):
        self.assertTrue(scoring.score_items([], []))
        self.assertFalse(scoring.score_items(GOOD["items"], []))

    def test_same_product_twice_matches_one_to_one(self):
        exp = [{"product": "beaker", "sku": "A", "quantity": 6}, {"product": "beaker", "sku": "B", "quantity": 6}]
        got = [{"product": "Beaker 250 ml", "sku": "A", "quantity": 6}, {"product": "Beaker 500 ml", "sku": "B", "quantity": 6}]
        self.assertTrue(scoring.score_items(got, exp))
        self.assertFalse(scoring.score_items([got[0], got[0]], exp))


class SummaryTests(unittest.TestCase):
    def test_summary_counts(self):
        results = [scoring.score_case(GOOD, EXP), scoring.score_case(None, EXP),
                   scoring.score_case(dict(GOOD, status="Cancelled"), EXP)]
        s = scoring.summarise(results)
        self.assertEqual((s["cases"], s["passed"], s["invalid_json"]), (3, 1, 1))
        self.assertEqual(s["fields"]["supplier"], {"correct": 2, "scored": 3})


if __name__ == "__main__":
    unittest.main()
