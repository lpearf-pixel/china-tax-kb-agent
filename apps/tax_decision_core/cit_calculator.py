from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .domain import CalculationResult

CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class CitCalculationContext:
    calculation_id: str
    accounting_profit: Decimal | None
    adjustment_increase: Decimal | None
    adjustment_decrease: Decimal | None
    loss_carryforward: Decimal | None
    tax_rate: Decimal | None
    taxable_income_ratio: Decimal | None = Decimal("1")
    tax_credit: Decimal | None = Decimal("0")
    prepaid_tax: Decimal | None = Decimal("0")
    payment_due_date: date | None = None
    rule_ids: list[str] = field(default_factory=list)


class CitCalculator:
    FACT_FIELDS = {
        "accounting_profit": "cit.accounting_profit",
        "adjustment_increase": "cit.adjustment_increase",
        "adjustment_decrease": "cit.adjustment_decrease",
        "loss_carryforward": "cit.loss_carryforward",
        "tax_rate": "cit.tax_rate",
        "taxable_income_ratio": "cit.taxable_income_ratio",
        "tax_credit": "cit.tax_credit",
        "prepaid_tax": "cit.prepaid_tax",
    }

    def calculate(self, context: CitCalculationContext) -> CalculationResult:
        missing = [
            fact_id
            for field_name, fact_id in self.FACT_FIELDS.items()
            if getattr(context, field_name) is None
        ]
        if missing:
            return CalculationResult(
                calculation_id=context.calculation_id,
                status="unable_to_calculate",
                tax_type="企业所得税",
                inputs={"calculation_basis": "会计利润纳税调整桥接"},
                missing_fact_ids=missing,
                formula="缺少企业所得税计算输入，停止确定性计算。",
                rule_ids=list(context.rule_ids),
            )

        raw_taxable = (
            context.accounting_profit
            + context.adjustment_increase
            - context.adjustment_decrease
            - context.loss_carryforward
        )
        loss_candidate = _q(-raw_taxable) if raw_taxable < 0 else Decimal("0.00")
        taxable = _q(max(raw_taxable, Decimal("0")))
        preferred_base = _q(taxable * context.taxable_income_ratio)
        tax_amount = _q(preferred_base * context.tax_rate)
        payable = _q(tax_amount - context.tax_credit - context.prepaid_tax)
        events: list[dict] = []
        if context.payment_due_date and payable != 0:
            events.append(
                {
                    "date": context.payment_due_date.isoformat(),
                    "type": "tax_payment" if payable > 0 else "refund_candidate",
                    "amount": str(abs(payable)),
                    "tax_type": "企业所得税",
                }
            )
        formula = (
            "应纳税所得额=(会计利润+纳税调增-纳税调减-可弥补亏损)；"
            f"应纳所得税额=max(应纳税所得额,0)×{context.taxable_income_ratio}×{context.tax_rate}；"
            "应补退税额=应纳所得税额-税额抵免-已预缴税额"
        )
        return CalculationResult(
            calculation_id=context.calculation_id,
            status="determinate",
            tax_type="企业所得税",
            taxable_amount=taxable,
            tax_amount=tax_amount,
            payable_or_credit=payable,
            formula=formula,
            inputs={
                "accounting_profit": context.accounting_profit,
                "adjustment_increase": context.adjustment_increase,
                "adjustment_decrease": context.adjustment_decrease,
                "loss_carryforward": context.loss_carryforward,
                "raw_taxable_income": _q(raw_taxable),
                "taxable_income_ratio": context.taxable_income_ratio,
                "tax_rate": context.tax_rate,
                "tax_credit": context.tax_credit,
                "prepaid_tax": context.prepaid_tax,
                "loss_candidate": loss_candidate,
            },
            rule_ids=list(context.rule_ids),
            cashflow_events=events,
        )
