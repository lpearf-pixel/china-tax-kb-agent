import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "11-问题测试集" / "v7_2_1_pit_cases.jsonl"


def amount(value):
    if value is None:
        return None
    if isinstance(value, dict) and value.get("__type__") == "decimal":
        return Decimal(str(value["value"]))
    return Decimal(str(value))


class V721PitCorpusTests(unittest.TestCase):
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
                pit = next((row for row in result.calculations if row["tax_type"] == "个人所得税"), None)
                if expected.get("status"):
                    self.assertIsNotNone(pit)
                    self.assertEqual(pit["status"], expected["status"])
                if expected.get("tax") is not None:
                    self.assertEqual(amount(pit["tax_amount"]), Decimal(expected["tax"]))
                if expected.get("payable") is not None:
                    self.assertEqual(amount(pit["payable_or_credit"]), Decimal(expected["payable"]))
                if expected.get("rule_absent"):
                    self.assertNotIn(expected["rule_absent"], pit["rule_ids"])
                if "review" in expected:
                    self.assertEqual(result.human_review_required, expected["review"])
                if expected.get("missing"):
                    self.assertIn(expected["missing"], result.missing_facts)
                if expected.get("annual_settlement"):
                    self.assertTrue(pit["inputs"]["annual_settlement_required"])
                    self.assertIn("年度汇算", result.initial_conclusion)
                if expected.get("discount"):
                    self.assertGreater(amount(pit["inputs"]["half_reduction"]), Decimal("0"))
                if expected.get("tax_types"):
                    self.assertEqual({row["tax_type"] for row in result.calculations}, set(expected["tax_types"]))
                if expected.get("breakdown"):
                    self.assertTrue(result.schemes)
                    for tax_type in expected["tax_types"]:
                        self.assertIn(tax_type, result.schemes[0].tax_breakdown)


if __name__ == "__main__":
    unittest.main()
