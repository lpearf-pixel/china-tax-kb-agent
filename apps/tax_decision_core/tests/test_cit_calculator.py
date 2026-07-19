import unittest
from datetime import date
from decimal import Decimal

from apps.tax_decision_core.cit_calculator import CitCalculationContext, CitCalculator


class CitCalculatorTests(unittest.TestCase):
    def calculate(self, **overrides):
        data = {
            "calculation_id": "cit-test",
            "accounting_profit": Decimal("1000000"),
            "adjustment_increase": Decimal("0"),
            "adjustment_decrease": Decimal("0"),
            "loss_carryforward": Decimal("0"),
            "tax_rate": Decimal("0.25"),
            "taxable_income_ratio": Decimal("1"),
            "tax_credit": Decimal("0"),
            "prepaid_tax": Decimal("0"),
            "payment_due_date": date(2027, 5, 31),
            "rule_ids": ["CIT-RESIDENT-GENERAL-RATE-25"],
        }
        data.update(overrides)
        return CitCalculator().calculate(CitCalculationContext(**data))

    def test_general_enterprise_one_million_taxable_income_is_250k(self):
        result = self.calculate()
        self.assertEqual(result.taxable_amount, Decimal("1000000.00"))
        self.assertEqual(result.tax_amount, Decimal("250000.00"))
        self.assertEqual(result.payable_or_credit, Decimal("250000.00"))

    def test_small_low_profit_effective_tax_is_five_percent(self):
        result = self.calculate(
            tax_rate=Decimal("0.20"),
            taxable_income_ratio=Decimal("0.25"),
            rule_ids=[
                "CIT-SMALL-LOW-PROFIT-TAXABLE-RATIO-2023-2027",
                "CIT-SMALL-LOW-PROFIT-RATE-2023-2027",
            ],
        )
        self.assertEqual(result.tax_amount, Decimal("50000.00"))

    def test_loss_produces_zero_current_tax_and_loss_candidate(self):
        result = self.calculate(accounting_profit=Decimal("-100000"))
        self.assertEqual(result.tax_amount, Decimal("0.00"))
        self.assertEqual(result.inputs["loss_candidate"], Decimal("100000.00"))

    def test_credit_and_prepaid_tax_create_refund_candidate(self):
        result = self.calculate(
            accounting_profit=Decimal("100000"),
            tax_credit=Decimal("10000"),
            prepaid_tax=Decimal("20000"),
        )
        self.assertEqual(result.tax_amount, Decimal("25000.00"))
        self.assertEqual(result.payable_or_credit, Decimal("-5000.00"))

    def test_missing_accounting_profit_fails_closed(self):
        result = self.calculate(accounting_profit=None)
        self.assertEqual(result.status, "unable_to_calculate")
        self.assertIn("cit.accounting_profit", result.missing_fact_ids)


if __name__ == "__main__":
    unittest.main()
