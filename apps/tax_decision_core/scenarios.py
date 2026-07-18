from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from .domain import (
    CalculationResult,
    CaseRecord,
    RuleEvaluation,
    RuleEvaluationStatus,
    Scenario,
    TaxIssue,
)

ALLOWED_DECISION_VARIABLES = {
    "waive_exemption",
    "invoice_type",
    "pricing_mode",
    "collection_timing",
    "voluntary_general_taxpayer",
}


@dataclass(slots=True, frozen=True)
class PlanningObjective:
    tax_burden: Decimal = Decimal("0.25")
    cashflow: Decimal = Decimal("0.15")
    certainty: Decimal = Decimal("0.20")
    completeness: Decimal = Decimal("0.10")
    complexity: Decimal = Decimal("0.10")
    risk: Decimal = Decimal("0.15")
    invoice_satisfaction: Decimal = Decimal("0.05")
    desired_invoice_type: str = ""


@dataclass(slots=True)
class ScenarioScore:
    scenario_id: str
    total_score: Decimal
    components: dict[str, Decimal] = field(default_factory=dict)


class ScenarioEngine:
    def generate(
        self,
        case: CaseRecord,
        issues: list[TaxIssue],
        evaluations: list[RuleEvaluation],
        calculations: list[CalculationResult],
    ) -> list[Scenario]:
        review = any(
            evaluation.status
            in {RuleEvaluationStatus.CONFLICT, RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED}
            for evaluation in evaluations
        )
        review = review or any(issue.risk_level == "high" for issue in issues)
        issue_ids = {issue.issue_id for issue in issues}
        risks = [issue.issue_type for issue in issues if issue.risk_level in {"medium", "high"}]
        required_documents = ["合同", "发票与申报资料", "收付款记录"]
        if "vat-hi-special" in issue_ids:
            required_documents += [
                "享惠主体证明",
                "HS编码归类资料",
                "报关与物流资料",
                "货物用途及流向台账",
            ]
            review = True

        scenarios: list[Scenario] = []
        for index, calculation in enumerate(calculations, 1):
            raw_variables = dict(calculation.inputs.get("decision_variables") or {})
            for key in ALLOWED_DECISION_VARIABLES:
                if key in calculation.inputs:
                    raw_variables.setdefault(key, calculation.inputs[key])
            decision_variables = {
                key: value for key, value in raw_variables.items() if key in ALLOWED_DECISION_VARIABLES
            }
            total_tax = (
                calculation.payable_or_credit
                if calculation.payable_or_credit is not None
                else calculation.tax_amount
            )
            if total_tax is not None and total_tax < 0:
                total_tax = Decimal("0")
            name = str(calculation.inputs.get("scenario_name") or f"方案{index}")
            scenario_review = review or calculation.status == "unable_to_calculate"
            payment_dates = [
                event.get("date")
                for event in calculation.cashflow_events
                if event.get("type") == "tax_payment" and event.get("date")
            ]
            scenarios.append(
                Scenario(
                    scenario_id=f"scenario-{calculation.calculation_id}",
                    name=name,
                    decision_variables=decision_variables,
                    calculation_ids=[calculation.calculation_id],
                    total_tax=total_tax,
                    cashflow_summary={
                        "payment_dates": payment_dates,
                        "calculation_status": calculation.status,
                        "missing_fact_count": len(calculation.missing_fact_ids),
                    },
                    risks=list(
                        dict.fromkeys(
                            risks + (["计算输入不足"] if calculation.missing_fact_ids else [])
                        )
                    ),
                    required_documents=list(dict.fromkeys(required_documents)),
                    human_review_required=scenario_review,
                )
            )

        if not scenarios:
            scenarios.append(
                Scenario(
                    scenario_id=f"scenario-{case.case_id}-insufficient",
                    name="资料补充与保守基线",
                    risks=["尚未形成可计算方案"],
                    required_documents=required_documents,
                    human_review_required=True,
                )
            )
        return scenarios

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def rank(
        self,
        scenarios: list[Scenario],
        objective: PlanningObjective | None = None,
    ) -> list[ScenarioScore]:
        objective = objective or PlanningObjective()
        known_taxes = [scenario.total_tax for scenario in scenarios if scenario.total_tax is not None]
        low = min(known_taxes) if known_taxes else Decimal("0")
        high = max(known_taxes) if known_taxes else Decimal("0")
        results: list[ScenarioScore] = []

        for scenario in scenarios:
            if scenario.total_tax is None:
                tax_score = Decimal("0")
            elif high == low:
                tax_score = Decimal("100")
            else:
                tax_score = (
                    Decimal("1") - (scenario.total_tax - low) / (high - low)
                ) * Decimal("100")

            status = str(scenario.cashflow_summary.get("calculation_status") or "")
            certainty = {
                "determinate": Decimal("100"),
                "conditional_determinate": Decimal("70"),
                "unable_to_calculate": Decimal("0"),
            }.get(status, Decimal("50"))
            missing_count = int(scenario.cashflow_summary.get("missing_fact_count") or 0)
            completeness = max(Decimal("0"), Decimal("100") - Decimal(missing_count * 25))
            complexity = max(
                Decimal("0"), Decimal("100") - Decimal(len(scenario.decision_variables) * 12)
            )
            risk = (
                Decimal("0")
                if scenario.human_review_required
                else (Decimal("65") if scenario.risks else Decimal("100"))
            )
            invoice_type = str(scenario.decision_variables.get("invoice_type") or "")
            invoice = (
                Decimal("100")
                if not objective.desired_invoice_type
                or invoice_type == objective.desired_invoice_type
                else Decimal("30")
            )
            payment_dates = scenario.cashflow_summary.get("payment_dates") or []
            cashflow = Decimal("70") if payment_dates else Decimal("50")
            components = {
                "tax_burden": self._q(tax_score),
                "cashflow": cashflow,
                "certainty": certainty,
                "completeness": completeness,
                "complexity": complexity,
                "risk": risk,
                "invoice_satisfaction": invoice,
            }
            total = (
                components["tax_burden"] * objective.tax_burden
                + components["cashflow"] * objective.cashflow
                + components["certainty"] * objective.certainty
                + components["completeness"] * objective.completeness
                + components["complexity"] * objective.complexity
                + components["risk"] * objective.risk
                + components["invoice_satisfaction"] * objective.invoice_satisfaction
            )
            scenario.score_components = {key: self._q(value) for key, value in components.items()}
            scenario.total_score = self._q(total)
            results.append(
                ScenarioScore(
                    scenario_id=scenario.scenario_id,
                    total_score=scenario.total_score,
                    components=scenario.score_components,
                )
            )

        results.sort(key=lambda item: (item.total_score, item.scenario_id), reverse=True)
        return results
