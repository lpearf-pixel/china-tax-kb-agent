import unittest
from datetime import date
from decimal import Decimal

from apps.tax_decision_core.pit_calculator import (
    PitBusinessCalculationContext,
    PitLaborCalculationContext,
    PitCalculator,
)


class PitCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.calculator = PitCalculator()

    def business(self, **overrides):
        data = {
            "calculation_id": "pit-business",
            "taxable_income": Decimal("1000000"),
            "other_tax_reduction": Decimal("0"),
            "prepaid_tax": Decimal("0"),
            "individual_business_half_reduction": False,
            "payment_due_date": date(2027, 3, 31),
            "rule_ids": ["PIT-BUSINESS-INCOME-RATE-TABLE"],
        }
        data.update(overrides)
        return self.calculator.calculate_business(PitBusinessCalculationContext(**data))

    def labor(self, gross):
        return self.calculator.calculate_labor(PitLaborCalculationContext(
            calculation_id="pit-labor",
            gross_income=Decimal(str(gross)),
            already_withheld=Decimal("0"),
            payment_due_date=date(2026, 8, 15),
            rule_ids=["PIT-LABOR-REMUNERATION-RESIDENT-WITHHOLDING"],
        ))

    def test_business_income_rate_boundaries(self):
        expected = {
            "30000": "1500.00",
            "90000": "7500.00",
            "300000": "49500.00",
            "500000": "109500.00",
            "1000000": "284500.00",
        }
        for taxable, tax in expected.items():
            with self.subTest(taxable=taxable):
                self.assertEqual(self.business(taxable_income=Decimal(taxable)).tax_amount, Decimal(tax))

    def test_individual_business_half_reduction_on_one_million(self):
        result = self.business(individual_business_half_reduction=True)
        self.assertEqual(result.tax_amount, Decimal("142250.00"))

    def test_business_refund_candidate_after_prepaid_tax(self):
        result = self.business(taxable_income=Decimal("30000"), prepaid_tax=Decimal("2000"))
        self.assertEqual(result.payable_or_credit, Decimal("-500.00"))

    def test_labor_remuneration_withholding_boundaries(self):
        expected = {
            "3000": "440.00",
            "10000": "1600.00",
            "30000": "5200.00",
            "80000": "18600.00",
        }
        for gross, tax in expected.items():
            with self.subTest(gross=gross):
                result = self.labor(gross)
                self.assertEqual(result.tax_amount, Decimal(tax))
                self.assertTrue(result.inputs["annual_settlement_required"])

    def test_missing_inputs_fail_closed(self):
        result = self.calculator.calculate_business(PitBusinessCalculationContext(
            calculation_id="missing", taxable_income=None,
            other_tax_reduction=Decimal("0"), prepaid_tax=Decimal("0"),
            individual_business_half_reduction=False,
        ))
        self.assertEqual(result.status, "unable_to_calculate")
        self.assertIn("pit.business_taxable_income", result.missing_fact_ids)


if __name__ == "__main__":
    unittest.main()
