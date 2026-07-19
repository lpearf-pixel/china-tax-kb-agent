import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "11-问题测试集" / "v7_2_cit_cases.jsonl"


def amount(value):
    if value is None:
        return None
    if isinstance(value, dict) and value.get("__type__") == "decimal":
        return Decimal(str(value["value"]))
    return Decimal(str(value))


class V72CitCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.service = TaxPlanningService(ROOT, case_root=Path(cls.temp.name))
        cls.cases = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_corpus_has_twenty_unique_cases(self):
        self.assertGreaterEqual(len(self.cases), 20)
        ids = [item["id"] for item in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_declared_expectations(self):
        for item in self.cases:
            with self.subTest(case_id=item["id"]):
                result = self.service.analyze(TaxFacts.from_dict(item["facts"]))
                expected = item["expected"]
                calculations = result.calculations
                cit = next((row for row in calculations if row["tax_type"] == "企业所得税"), None)
                if expected.get("status"):
                    self.assertIsNotNone(cit)
                    self.assertEqual(cit["status"], expected["status"])
                if expected.get("tax") is not None:
                    self.assertEqual(amount(cit["tax_amount"]), Decimal(expected["tax"]))
                if expected.get("taxable") is not None:
                    self.assertEqual(amount(cit["taxable_amount"]), Decimal(expected["taxable"]))
                if expected.get("payable") is not None:
                    self.assertEqual(amount(cit["payable_or_credit"]), Decimal(expected["payable"]))
                if expected.get("rule"):
                    self.assertIn(expected["rule"], cit["rule_ids"])
                if expected.get("rule_absent"):
                    self.assertNotIn(expected["rule_absent"], cit["rule_ids"])
                if "review" in expected:
                    self.assertEqual(result.human_review_required, expected["review"])
                if expected.get("missing"):
                    self.assertIn(expected["missing"], result.missing_facts)
                if expected.get("tax_types"):
                    self.assertEqual({row["tax_type"] for row in calculations}, set(expected["tax_types"]))
                if expected.get("breakdown"):
                    self.assertTrue(result.schemes)
                    self.assertIn("增值税", result.schemes[0].tax_breakdown)
                    self.assertIn("企业所得税", result.schemes[0].tax_breakdown)


if __name__ == "__main__":
    unittest.main()
