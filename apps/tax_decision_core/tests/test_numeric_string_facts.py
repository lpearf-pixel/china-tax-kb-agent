from __future__ import annotations

import unittest
from datetime import date

from apps.tax_decision_core.domain import RuleEvaluationStatus
from apps.tax_decision_core.rule_engine import RuleEngine
from apps.tax_decision_core.rule_schema import RuleDefinition


class NumericStringFactTests(unittest.TestCase):
    def rule(self):
        return RuleDefinition.from_mapping(
            {
                "rule_id": "TEST-NUMERIC-STRING",
                "version": 1,
                "status": "effective",
                "valid_from": "2026-01-01",
                "valid_to": "2027-12-31",
                "jurisdiction": "CN",
                "tax_type": "增值税",
                "priority": 100,
                "when": {
                    "fact": "transaction.total_sales_same_period",
                    "operator": "less_or_equal",
                    "value": 300000,
                },
                "then": {
                    "outcome": "threshold_exempt_candidate",
                    "value": True,
                },
                "requires": ["transaction.total_sales_same_period"],
                "legal_basis": [{"document_id": "DOC-TEST"}],
            }
        )

    def test_numeric_string_is_compared_as_decimal(self):
        result = RuleEngine().evaluate(
            self.rule(),
            {"transaction.total_sales_same_period": "240000.00"},
            date(2026, 7, 17),
        )
        self.assertEqual(result.status, RuleEvaluationStatus.APPLICABLE)

    def test_invalid_numeric_string_does_not_execute_or_silently_match(self):
        with self.assertRaises(TypeError):
            RuleEngine().evaluate(
                self.rule(),
                {"transaction.total_sales_same_period": "not-a-number"},
                date(2026, 7, 17),
            )


if __name__ == "__main__":
    unittest.main()
