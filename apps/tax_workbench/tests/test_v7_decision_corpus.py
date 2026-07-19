from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.markdown import render_markdown
from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "11-问题测试集" / "v7_decision_cases.jsonl"


def decoded(value):
    if isinstance(value, dict) and value.get("__type__") == "decimal":
        return Decimal(str(value["value"]))
    if value in (None, ""):
        return None
    return Decimal(str(value))


class V7DecisionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.service = TaxPlanningService(ROOT, case_root=Path(cls.temp.name))
        cls.cases = [
            json.loads(line)
            for line in CORPUS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_corpus_has_at_least_twenty_unique_cases(self):
        self.assertGreaterEqual(len(self.cases), 20)
        ids = [item["id"] for item in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_factual_cases_meet_declared_expectations(self):
        factual = [item for item in self.cases if item.get("facts")]
        self.assertGreaterEqual(len(factual), 15)
        for item in factual:
            with self.subTest(case_id=item["id"]):
                payload = dict(item["facts"])
                payload.setdefault("description", item.get("description", "税务决策回归场景"))
                payload.setdefault("objective", "合规降负")
                facts = TaxFacts.from_dict(payload)
                result = self.service.analyze(facts)
                expected = item.get("expected", {})
                evaluations = {
                    entry.get("rule_id"): entry for entry in result.rule_trace
                }
                rule_ids = set(evaluations)
                issue_ids = {entry.get("issue_id") for entry in result.issues}

                if expected.get("rule"):
                    self.assertIn(expected["rule"], rule_ids)
                if expected.get("rule_not_loaded"):
                    self.assertNotIn(expected["rule_not_loaded"], rule_ids)
                if expected.get("issue"):
                    self.assertIn(expected["issue"], issue_ids)
                if "review" in expected:
                    self.assertEqual(
                        result.human_review_required,
                        expected["review"],
                    )
                if expected.get("review_or_missing"):
                    self.assertTrue(
                        result.human_review_required or bool(result.missing_facts)
                    )
                if expected.get("missing"):
                    self.assertIn(expected["missing"], result.missing_facts)
                if expected.get("levy_rate") and expected.get("rule"):
                    self.assertEqual(
                        decoded(evaluations[expected["rule"]].get("value")),
                        Decimal(expected["levy_rate"]),
                    )
                if expected.get("calculation_status"):
                    self.assertEqual(
                        result.calculations[0]["status"],
                        expected["calculation_status"],
                    )
                if expected.get("tax"):
                    self.assertEqual(
                        decoded(result.calculations[0].get("tax_amount")),
                        Decimal(expected["tax"]),
                    )
                if expected.get("taxable_amount"):
                    self.assertEqual(
                        decoded(result.calculations[0].get("taxable_amount")),
                        Decimal(expected["taxable_amount"]),
                    )
                if expected.get("tax_positive"):
                    amounts = [
                        decoded(entry.get("tax_amount"))
                        for entry in result.calculations
                    ]
                    self.assertTrue(
                        any(value is not None and value > 0 for value in amounts)
                    )
                if expected.get("scenario"):
                    self.assertIn(
                        expected["scenario"],
                        {scheme.name for scheme in result.schemes},
                    )
                if expected.get("report_sections"):
                    report = render_markdown(facts, result)
                    for section in expected["report_sections"]:
                        self.assertIn(section, report)


if __name__ == "__main__":
    unittest.main()
