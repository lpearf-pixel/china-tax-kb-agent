from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .domain import CalculationResult, Scenario


@dataclass(slots=True)
class MultiTaxScenario(Scenario):
    tax_breakdown: dict[str, Decimal] = field(default_factory=dict)


class MultiTaxScenarioAggregator:
    """Combine tax-specific calculations without offsetting tax types."""

    @staticmethod
    def _copy_scenario(source: Scenario) -> MultiTaxScenario:
        existing = dict(getattr(source, "tax_breakdown", {}) or {})
        if not existing and source.total_tax is not None:
            existing["增值税"] = max(source.total_tax, Decimal("0"))
        return MultiTaxScenario(
            scenario_id=source.scenario_id,
            name=source.name,
            decision_variables=dict(source.decision_variables),
            calculation_ids=list(source.calculation_ids),
            total_tax=source.total_tax,
            cashflow_summary=dict(source.cashflow_summary),
            score_components=dict(source.score_components),
            total_score=source.total_score,
            risks=list(source.risks),
            required_documents=list(source.required_documents),
            human_review_required=source.human_review_required,
            tax_breakdown=existing,
        )

    def combine(
        self,
        base_scenarios: list[Scenario],
        shared_calculations: list[CalculationResult],
    ) -> list[MultiTaxScenario]:
        sources = base_scenarios or [
            Scenario(
                scenario_id="scenario-cit-baseline",
                name="企业所得税合规基线",
                total_tax=None,
            )
        ]
        results: list[MultiTaxScenario] = []
        for source in sources:
            scenario = self._copy_scenario(source)
            refund_candidates = dict(
                scenario.cashflow_summary.get("refund_candidates") or {}
            )
            for calculation in shared_calculations:
                if calculation.calculation_id not in scenario.calculation_ids:
                    scenario.calculation_ids.append(calculation.calculation_id)
                amount = (
                    calculation.payable_or_credit
                    if calculation.payable_or_credit is not None
                    else calculation.tax_amount
                )
                if calculation.status == "unable_to_calculate" or amount is None:
                    scenario.human_review_required = True
                    risk = f"{calculation.tax_type}计算输入不足"
                    if risk not in scenario.risks:
                        scenario.risks.append(risk)
                    scenario.tax_breakdown.setdefault(calculation.tax_type, Decimal("0"))
                    continue
                if amount < 0:
                    refund_candidates[calculation.tax_type] = abs(amount)
                    scenario.tax_breakdown[calculation.tax_type] = Decimal("0")
                else:
                    scenario.tax_breakdown[calculation.tax_type] = amount
            if refund_candidates:
                scenario.cashflow_summary["refund_candidates"] = refund_candidates
            scenario.total_tax = sum(
                (max(value, Decimal("0")) for value in scenario.tax_breakdown.values()),
                Decimal("0"),
            )
            results.append(scenario)
        return results
