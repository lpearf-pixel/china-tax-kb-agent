from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .domain import CalculationResult


@dataclass(slots=True)
class CalculationContext:
    calculation_id: str
    taxpayer_status: str
    amount: Decimal | None
    amount_tax_inclusive: bool = False
    levy_rate: Decimal | None = None
    threshold_exempt_candidate: bool = False
    waive_exemption: bool = False
    invoice_type: str = ""
    deductible_input_tax: Decimal = Decimal("0")
    prepaid_tax: Decimal = Decimal("0")
    transaction_date: date | None = None
    filing_due_date: date | None = None
    payment_due_date: date | None = None
    rule_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("amount", "levy_rate", "deductible_input_tax", "prepaid_tax"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                setattr(self, name, Decimal(str(value)))
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount cannot be negative")
        if self.levy_rate is not None and self.levy_rate < 0:
            raise ValueError("levy_rate cannot be negative")
        if self.deductible_input_tax < 0 or self.prepaid_tax < 0:
            raise ValueError("input and prepaid tax cannot be negative")


class VatCalculator:
    def __init__(self, config_path: Path | None = None):
        path = config_path or Path(__file__).resolve().parent / "config" / "rounding.json"
        config = {"quantum": "0.01", "mode": "ROUND_HALF_UP"}
        if Path(path).exists():
            config.update(json.loads(Path(path).read_text(encoding="utf-8")))
        if config["mode"] != "ROUND_HALF_UP":
            raise ValueError("only ROUND_HALF_UP is supported")
        self.quantum = Decimal(str(config["quantum"]))
        self.rounding = ROUND_HALF_UP

    def _q(self, value: Decimal) -> Decimal:
        return value.quantize(self.quantum, rounding=self.rounding)

    def _timeline(self, context: CalculationContext, payable: Decimal | None) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        if context.transaction_date:
            events.append({"type": "tax_point_reference", "date": context.transaction_date.isoformat(), "amount": "0.00"})
        if context.filing_due_date:
            events.append({"type": "filing_due", "date": context.filing_due_date.isoformat(), "amount": "0.00"})
        if context.payment_due_date and payable is not None:
            events.append({"type": "tax_payment" if payable >= 0 else "tax_credit", "date": context.payment_due_date.isoformat(), "amount": str(self._q(payable))})
        return events

    def calculate(self, context: CalculationContext) -> CalculationResult:
        missing: list[str] = []
        if context.amount is None:
            missing.append("transaction.amount")
        exempt = context.threshold_exempt_candidate and not context.waive_exemption
        if not exempt and context.levy_rate is None:
            missing.append("calculation.levy_rate")
        if missing:
            return CalculationResult(calculation_id=context.calculation_id, status="unable_to_calculate", tax_type="增值税", inputs={"taxpayer_status": context.taxpayer_status}, rule_ids=list(context.rule_ids), missing_fact_ids=missing, formula="缺少必要计算输入，未执行税额计算")
        assert context.amount is not None
        amount = context.amount
        if exempt:
            taxable = self._q(amount)
            tax = Decimal("0.00")
            payable = self._q(tax - context.prepaid_tax)
            formula = "符合起征点候选且未放弃免税：应纳增值税 = 0.00"
            status = "determinate"
        else:
            assert context.levy_rate is not None
            rate = context.levy_rate
            if context.amount_tax_inclusive:
                taxable = self._q(amount / (Decimal("1") + rate))
                tax = self._q(amount - taxable)
                formula = f"{amount} ÷ (1 + {rate}) = {taxable}；增值税 = {amount} - {taxable} = {tax}"
            else:
                taxable = self._q(amount)
                tax = self._q(taxable * rate)
                formula = f"{taxable} × {rate} = {tax}"
            if context.taxpayer_status == "一般纳税人":
                payable = self._q(tax - context.deductible_input_tax - context.prepaid_tax)
                if payable < 0:
                    formula += f"；销项{tax} - 进项{self._q(context.deductible_input_tax)} - 预缴{self._q(context.prepaid_tax)} = {payable}，形成留抵候选"
                else:
                    formula += f"；销项{tax} - 进项{self._q(context.deductible_input_tax)} - 预缴{self._q(context.prepaid_tax)} = {payable}"
            else:
                payable = self._q(tax - context.prepaid_tax)
                if context.prepaid_tax:
                    formula += f"；税额{tax} - 预缴{self._q(context.prepaid_tax)} = {payable}"
            status = "conditional_determinate" if context.threshold_exempt_candidate and context.waive_exemption else "determinate"
        return CalculationResult(calculation_id=context.calculation_id, status=status, tax_type="增值税", taxable_amount=taxable, tax_amount=tax, deductible_input_tax=self._q(context.deductible_input_tax), payable_or_credit=payable, formula=formula, inputs={"amount": amount, "amount_tax_inclusive": context.amount_tax_inclusive, "levy_rate": context.levy_rate, "threshold_exempt_candidate": context.threshold_exempt_candidate, "waive_exemption": context.waive_exemption, "invoice_type": context.invoice_type, "prepaid_tax": context.prepaid_tax}, rule_ids=list(context.rule_ids), cashflow_events=self._timeline(context, payable), rounding=f"ROUND_HALF_UP:{self.quantum}")
