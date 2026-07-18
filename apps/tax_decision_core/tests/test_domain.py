from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from apps.tax_decision_core.domain import (
    CalculationResult,
    CaseRecord,
    CaseState,
    FactStatus,
    FactVersion,
    Scenario,
)


class DomainModelTests(unittest.TestCase):
    def test_fact_version_round_trips_decimal_date_and_datetime(self):
        fact = FactVersion(
            fact_id="transaction.sales_amount",
            version=2,
            value=Decimal("240000.10"),
            status=FactStatus.CONFIRMED,
            source="user_confirmed",
            valid_from=date(2026, 7, 1),
            system_time=datetime(2026, 7, 18, 8, 30, tzinfo=timezone.utc),
            actor="owner",
        )

        restored = FactVersion.from_dict(fact.to_dict())

        self.assertEqual(restored, fact)
        self.assertIsInstance(restored.value, Decimal)
        self.assertIsInstance(restored.valid_from, date)
        self.assertIsInstance(restored.system_time, datetime)

    def test_rejects_unknown_fact_status(self):
        payload = {
            "fact_id": "transaction.sales_amount",
            "version": 1,
            "value": {"__type__": "decimal", "value": "10"},
            "status": "guessed",
            "source": "test",
            "valid_from": None,
            "valid_to": None,
            "system_time": "2026-07-18T00:00:00+00:00",
            "actor": "test",
        }
        with self.assertRaises(ValueError):
            FactVersion.from_dict(payload)

    def test_case_state_is_validated_and_case_round_trips(self):
        case = CaseRecord(
            case_id="case-001",
            state=CaseState.DRAFT,
            kb_version="KB-2026.07.17-V5-PILOT-XJ-HI",
            rule_set_version="vat-rules-v1",
            facts_version=1,
            created_at=datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 18, 1, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(CaseRecord.from_dict(case.to_dict()), case)

        payload = case.to_dict()
        payload["state"] = "magic_complete"
        with self.assertRaises(ValueError):
            CaseRecord.from_dict(payload)

    def test_calculation_and_scenario_use_decimal_values(self):
        calculation = CalculationResult(
            calculation_id="calc-1",
            status="determinate",
            tax_type="增值税",
            taxable_amount=Decimal("1000000.00"),
            tax_amount=Decimal("10000.00"),
            formula="1000000.00 × 1%",
            rule_ids=["VAT-SMALL-1PCT-2026"],
        )
        scenario = Scenario(
            scenario_id="scenario-1",
            name="合规基线",
            decision_variables={"waive_exemption": False},
            calculation_ids=[calculation.calculation_id],
            total_tax=calculation.tax_amount,
            score_components={"certainty": Decimal("1.0")},
        )

        self.assertIsInstance(CalculationResult.from_dict(calculation.to_dict()).tax_amount, Decimal)
        self.assertIsInstance(Scenario.from_dict(scenario.to_dict()).total_tax, Decimal)


if __name__ == "__main__":
    unittest.main()
