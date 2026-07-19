from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .domain import CalculationResult

CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _business_tax(taxable: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    taxable = max(taxable, Decimal("0"))
    if taxable <= Decimal("30000"):
        rate, quick = Decimal("0.05"), Decimal("0")
    elif taxable <= Decimal("90000"):
        rate, quick = Decimal("0.10"), Decimal("1500")
    elif taxable <= Decimal("300000"):
        rate, quick = Decimal("0.20"), Decimal("10500")
    elif taxable <= Decimal("500000"):
        rate, quick = Decimal("0.30"), Decimal("40500")
    else:
        rate, quick = Decimal("0.35"), Decimal("65500")
    return _q(max(taxable * rate - quick, Decimal("0"))), rate, quick


def _labor_tax(taxable: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    if taxable <= Decimal("20000"):
        rate, quick = Decimal("0.20"), Decimal("0")
    elif taxable <= Decimal("50000"):
        rate, quick = Decimal("0.30"), Decimal("2000")
    else:
        rate, quick = Decimal("0.40"), Decimal("7000")
    return _q(max(taxable * rate - quick, Decimal("0"))), rate, quick


@dataclass(slots=True)
class PitBusinessCalculationContext:
    calculation_id: str
    taxable_income: Decimal | None
    other_tax_reduction: Decimal | None
    prepaid_tax: Decimal | None
    individual_business_half_reduction: bool
    payment_due_date: date | None = None
    rule_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PitLaborCalculationContext:
    calculation_id: str
    gross_income: Decimal | None
    already_withheld: Decimal | None
    payer_has_withholding_obligation: bool | None = True
    payment_due_date: date | None = None
    rule_ids: list[str] = field(default_factory=list)


class PitCalculator:
    def calculate_business(self, context: PitBusinessCalculationContext) -> CalculationResult:
        missing = []
        if context.taxable_income is None:
            missing.append("pit.business_taxable_income")
        if context.other_tax_reduction is None:
            missing.append("pit.business_other_tax_reduction")
        if context.prepaid_tax is None:
            missing.append("pit.business_prepaid_tax")
        if missing:
            return CalculationResult(
                context.calculation_id, "unable_to_calculate", "个人所得税",
                formula="缺少经营所得年度计算输入，停止确定性计算。",
                missing_fact_ids=missing, rule_ids=list(context.rule_ids),
            )
        taxable = _q(max(context.taxable_income, Decimal("0")))
        base_tax, rate, quick = _business_tax(taxable)
        other = _q(max(context.other_tax_reduction, Decimal("0")))
        discount = Decimal("0.00")
        capped = min(taxable, Decimal("2000000"))
        if context.individual_business_half_reduction and taxable > 0:
            capped_tax, _, _ = _business_tax(capped)
            allocated_other = _q(other * capped / taxable)
            discount = _q(max(capped_tax - allocated_other, Decimal("0")) * Decimal("0.5"))
        final_tax = _q(max(base_tax - other - discount, Decimal("0")))
        payable = _q(final_tax - context.prepaid_tax)
        events = []
        if context.payment_due_date and payable != 0:
            events.append({
                "date": context.payment_due_date.isoformat(),
                "type": "tax_payment" if payable > 0 else "refund_candidate",
                "amount": str(abs(payable)), "tax_type": "个人所得税",
            })
        return CalculationResult(
            context.calculation_id, "determinate", "个人所得税",
            taxable_amount=taxable, tax_amount=final_tax, payable_or_credit=payable,
            formula="基础税额=全年经营所得应纳税所得额×税率-速算扣除数；最终税额=基础税额-其他减免-个体工商户减半优惠；应补退候选=最终税额-已预缴税额",
            inputs={
                "base_tax": base_tax, "rate": rate, "quick_deduction": quick,
                "other_tax_reduction": other, "half_reduction": discount,
                "capped_preference_income": capped, "prepaid_tax": context.prepaid_tax,
            },
            rule_ids=list(context.rule_ids), cashflow_events=events,
        )

    def calculate_labor(self, context: PitLaborCalculationContext) -> CalculationResult:
        missing = []
        if context.gross_income is None:
            missing.append("pit.labor_gross_income")
        if context.already_withheld is None:
            missing.append("pit.labor_withheld_tax")
        if context.payer_has_withholding_obligation is not True:
            missing.append("pit.labor_payer_has_withholding_obligation")
        if missing:
            return CalculationResult(
                context.calculation_id, "unable_to_calculate", "个人所得税",
                formula="劳务报酬支付方扣缴义务或预扣输入未确认，停止确定性计算。",
                missing_fact_ids=missing, rule_ids=list(context.rule_ids),
            )
        gross = _q(max(context.gross_income, Decimal("0")))
        taxable = _q(max(gross - Decimal("800"), Decimal("0"))) if gross <= Decimal("4000") else _q(gross * Decimal("0.8"))
        withholding, rate, quick = _labor_tax(taxable)
        payable = _q(withholding - context.already_withheld)
        events = []
        if context.payment_due_date and payable != 0:
            events.append({
                "date": context.payment_due_date.isoformat(),
                "type": "withholding_tax" if payable > 0 else "withholding_refund_candidate",
                "amount": str(abs(payable)), "tax_type": "个人所得税",
            })
        return CalculationResult(
            context.calculation_id, "conditional_determinate", "个人所得税",
            taxable_amount=taxable, tax_amount=withholding, payable_or_credit=payable,
            formula="劳务报酬预扣应纳税所得额按800元或20%费用扣除确定；预扣税额=预扣应纳税所得额×预扣率-速算扣除数；居民个人年度终了后并入综合所得汇算",
            inputs={
                "gross_income": gross, "expense_deduction": _q(gross - taxable),
                "withholding_rate": rate, "quick_deduction": quick,
                "already_withheld": context.already_withheld,
                "payer_has_withholding_obligation": True,
                "annual_settlement_required": True,
            },
            rule_ids=list(context.rule_ids), cashflow_events=events,
        )
