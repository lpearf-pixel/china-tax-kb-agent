from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from apps.tax_decision_core.domain import (
    CalculationResult,
    CaseRecord,
    CaseState,
    RuleEvaluation,
    RuleEvaluationStatus,
    TaxIssue,
)
from apps.tax_decision_core.scenarios import PlanningObjective, ScenarioEngine


def case():
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return CaseRecord(
        "case-1",
        CaseState.CALCULATION_READY,
        "kb",
        "rules",
        1,
        now,
        now,
    )


class ScenarioTests(unittest.TestCase):
    def test_only_legal_decision_variables_are_kept(self):
        calculation = CalculationResult(
            "c1",
            "determinate",
            "增值税",
            tax_amount=Decimal("1000"),
            payable_or_credit=Decimal("1000"),
            inputs={
                "scenario_name": "专票方案",
                "decision_variables": {
                    "invoice_type": "专用发票",
                    "waive_exemption": True,
                    "fake_goods_flow": "Hainan",
                },
            },
        )
        scenarios = ScenarioEngine().generate(case(), [], [], [calculation])
        self.assertEqual(
            scenarios[0].decision_variables,
            {"invoice_type": "专用发票", "waive_exemption": True},
        )

    def test_transparent_scoring_ranks_lower_tax_with_same_risk(self):
        exempt = CalculationResult(
            "c1",
            "determinate",
            "增值税",
            payable_or_credit=Decimal("0"),
            inputs={
                "scenario_name": "免税",
                "decision_variables": {"invoice_type": "普通发票"},
            },
        )
        taxed = CalculationResult(
            "c2",
            "determinate",
            "增值税",
            payable_or_credit=Decimal("10000"),
            inputs={
                "scenario_name": "征税",
                "decision_variables": {"invoice_type": "专用发票"},
            },
        )
        engine = ScenarioEngine()
        scenarios = engine.generate(case(), [], [], [exempt, taxed])
        scores = engine.rank(
            scenarios,
            PlanningObjective(desired_invoice_type="普通发票"),
        )
        self.assertEqual(scores[0].scenario_id, "scenario-c1")
        self.assertEqual(
            set(scores[0].components),
            {
                "tax_burden",
                "cashflow",
                "certainty",
                "completeness",
                "complexity",
                "risk",
                "invoice_satisfaction",
            },
        )

    def test_hainan_special_issue_forces_review(self):
        issue = TaxIssue(
            "vat-hi-special",
            "增值税",
            "海南特殊政策",
            risk_level="high",
        )
        calculation = CalculationResult(
            "c1",
            "unable_to_calculate",
            "增值税",
            missing_fact_ids=["goods_flow.hs_code"],
        )
        scenario = ScenarioEngine().generate(
            case(),
            [issue],
            [RuleEvaluation("r", RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED)],
            [calculation],
        )[0]
        self.assertTrue(scenario.human_review_required)
        self.assertIn("HS编码归类资料", scenario.required_documents)


if __name__ == "__main__":
    unittest.main()
