import unittest
from decimal import Decimal

from apps.tax_decision_core.domain import CalculationResult, Scenario
from apps.tax_decision_core.multitax import MultiTaxScenarioAggregator


class MultiTaxAggregationTests(unittest.TestCase):
    def test_combines_vat_and_cit_without_cross_tax_offset(self):
        base = [Scenario("s1", "综合方案", total_tax=Decimal("1000"))]
        cit = CalculationResult(
            "cit-1",
            "determinate",
            "企业所得税",
            tax_amount=Decimal("2500"),
            payable_or_credit=Decimal("2500"),
        )
        result = MultiTaxScenarioAggregator().combine(base, [cit])[0]
        self.assertEqual(result.tax_breakdown["增值税"], Decimal("1000"))
        self.assertEqual(result.tax_breakdown["企业所得税"], Decimal("2500"))
        self.assertEqual(result.total_tax, Decimal("3500"))

    def test_refund_candidate_does_not_reduce_other_tax(self):
        base = [Scenario("s1", "综合方案", total_tax=Decimal("1000"))]
        cit = CalculationResult(
            "cit-refund",
            "determinate",
            "企业所得税",
            tax_amount=Decimal("500"),
            payable_or_credit=Decimal("-300"),
        )
        result = MultiTaxScenarioAggregator().combine(base, [cit])[0]
        self.assertEqual(result.tax_breakdown["企业所得税"], Decimal("0"))
        self.assertEqual(result.total_tax, Decimal("1000"))
        self.assertEqual(result.cashflow_summary["refund_candidates"]["企业所得税"], Decimal("300"))

    def test_unable_calculation_propagates_manual_review(self):
        base = [Scenario("s1", "综合方案", total_tax=Decimal("1000"))]
        cit = CalculationResult(
            "cit-missing",
            "unable_to_calculate",
            "企业所得税",
            missing_fact_ids=["cit.accounting_profit"],
        )
        result = MultiTaxScenarioAggregator().combine(base, [cit])[0]
        self.assertTrue(result.human_review_required)
        self.assertIn("企业所得税计算输入不足", result.risks)


if __name__ == "__main__":
    unittest.main()
