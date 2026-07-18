from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from apps.tax_decision_core.vat_calculator import CalculationContext, VatCalculator


class VatCalculatorTests(unittest.TestCase):
    def setUp(self): self.calculator = VatCalculator()

    def test_tax_inclusive_1010000_at_one_percent(self):
        result = self.calculator.calculate(CalculationContext(calculation_id="calc-inclusive", taxpayer_status="小规模纳税人", amount=Decimal("1010000"), amount_tax_inclusive=True, levy_rate=Decimal("0.01"), transaction_date=date(2026, 7, 18), payment_due_date=date(2026, 10, 20), rule_ids=["VAT-SMALL-1PCT-2026"]))
        self.assertEqual(result.status, "determinate")
        self.assertEqual(result.taxable_amount, Decimal("1000000.00"))
        self.assertEqual(result.tax_amount, Decimal("10000.00"))
        self.assertEqual(result.payable_or_credit, Decimal("10000.00"))
        self.assertIn("÷ (1 + 0.01)", result.formula)
        payment = next(item for item in result.cashflow_events if item["type"] == "tax_payment")
        self.assertEqual(payment["date"], "2026-10-20")

    def test_threshold_candidate_without_waiver_has_zero_vat(self):
        result = self.calculator.calculate(CalculationContext(calculation_id="calc-exempt", taxpayer_status="小规模纳税人", amount=Decimal("240000"), amount_tax_inclusive=False, threshold_exempt_candidate=True, waive_exemption=False, rule_ids=["VAT-SMALL-THRESHOLD-QUARTER-2026"]))
        self.assertEqual(result.status, "determinate")
        self.assertEqual(result.taxable_amount, Decimal("240000.00"))
        self.assertEqual(result.tax_amount, Decimal("0.00"))
        self.assertEqual(result.payable_or_credit, Decimal("0.00"))
        self.assertIn("起征点", result.formula)

    def test_waiving_exemption_recalculates_with_rate(self):
        result = self.calculator.calculate(CalculationContext(calculation_id="calc-waive", taxpayer_status="小规模纳税人", amount=Decimal("101000"), amount_tax_inclusive=True, threshold_exempt_candidate=True, waive_exemption=True, levy_rate=Decimal("0.01"), invoice_type="专用发票", rule_ids=["VAT-SMALL-1PCT-2026"]))
        self.assertEqual(result.taxable_amount, Decimal("100000.00"))
        self.assertEqual(result.tax_amount, Decimal("1000.00"))
        self.assertEqual(result.status, "conditional_determinate")

    def test_general_taxpayer_output_minus_input_and_credit(self):
        payable = self.calculator.calculate(CalculationContext(calculation_id="calc-general-pay", taxpayer_status="一般纳税人", amount=Decimal("1000000"), amount_tax_inclusive=False, levy_rate=Decimal("0.06"), deductible_input_tax=Decimal("20000")))
        self.assertEqual(payable.tax_amount, Decimal("60000.00"))
        self.assertEqual(payable.payable_or_credit, Decimal("40000.00"))
        credit = self.calculator.calculate(CalculationContext(calculation_id="calc-general-credit", taxpayer_status="一般纳税人", amount=Decimal("1000000"), amount_tax_inclusive=False, levy_rate=Decimal("0.06"), deductible_input_tax=Decimal("80000")))
        self.assertEqual(credit.payable_or_credit, Decimal("-20000.00"))
        self.assertIn("留抵", credit.formula)

    def test_missing_rate_returns_unable_to_calculate(self):
        result = self.calculator.calculate(CalculationContext(calculation_id="calc-missing", taxpayer_status="小规模纳税人", amount=Decimal("100000")))
        self.assertEqual(result.status, "unable_to_calculate")
        self.assertIn("calculation.levy_rate", result.missing_fact_ids)
        self.assertIsNone(result.tax_amount)


if __name__ == "__main__": unittest.main()
