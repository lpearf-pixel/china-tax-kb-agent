from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from apps.tax_decision_core.domain import Fact, FactGraph, FactStatus, FactVersion, RuleEvaluationStatus
from apps.tax_decision_core.rule_engine import RuleEngine
from apps.tax_decision_core.rule_schema import RuleDefinition


def make_graph(values: dict[str, object]) -> FactGraph:
    facts = {}
    for fact_id, value in values.items():
        version = FactVersion(fact_id=fact_id, version=1, value=value, status=FactStatus.CONFIRMED, source="test", system_time=datetime.now(timezone.utc), actor="test")
        facts[fact_id] = Fact(fact_id, [version])
    return FactGraph(facts=facts)


def make_rule(**overrides) -> RuleDefinition:
    data = {
        "rule_id": "VAT-QUARTER-THRESHOLD", "version": 1, "status": "effective",
        "valid_from": "2026-01-01", "valid_to": "2027-12-31", "jurisdiction": "CN",
        "tax_type": "增值税", "priority": 100, "exclusive_group": "vat_tax_treatment",
        "when": {"all": [
            {"fact": "taxpayer.vat_status", "operator": "equals", "value": "小规模纳税人"},
            {"fact": "transaction.amount_period", "operator": "equals", "value": "季度"},
            {"fact": "transaction.total_sales_same_period", "operator": "less_or_equal", "value": 300000},
            {"not": {"fact": "invoice.waive_exemption", "operator": "equals", "value": True}}
        ]},
        "then": {"outcome": "threshold_exempt", "value": True, "confidence": "deterministic"},
        "requires": ["transaction.total_sales_same_period", "invoice.waive_exemption"],
        "legal_basis": [{"document_id": "D", "provision_id": "P"}]
    }
    data.update(overrides)
    return RuleDefinition.from_mapping(data)


class RuleEngineTests(unittest.TestCase):
    def test_quarterly_240k_is_applicable_with_auditable_trace(self):
        graph = make_graph({"taxpayer.vat_status": "小规模纳税人", "transaction.amount_period": "季度", "transaction.total_sales_same_period": Decimal("240000"), "invoice.waive_exemption": False})
        result = RuleEngine().evaluate(make_rule(), graph, date(2026, 7, 18))
        self.assertEqual(result.status, RuleEvaluationStatus.APPLICABLE)
        self.assertEqual(result.outcome, "threshold_exempt")
        self.assertTrue(result.value)
        self.assertTrue(any(item.get("fact") == "transaction.total_sales_same_period" for item in result.trace))

    def test_missing_required_fact_returns_insufficient_facts(self):
        graph = make_graph({"taxpayer.vat_status": "小规模纳税人", "transaction.amount_period": "季度", "invoice.waive_exemption": False})
        result = RuleEngine().evaluate(make_rule(), graph, date(2026, 7, 18))
        self.assertEqual(result.status, RuleEvaluationStatus.INSUFFICIENT_FACTS)
        self.assertIn("transaction.total_sales_same_period", result.missing_fact_ids)

    def test_property_exclusion_at_higher_priority_wins_over_one_percent(self):
        graph = make_graph({"taxpayer.vat_status": "小规模纳税人", "transaction.transaction_type": "不动产", "transaction.original_levy_rate": Decimal("0.03")})
        one_percent = make_rule(rule_id="VAT-1PCT", priority=100, exclusive_group="vat_levy_rate", when={"all": [{"fact": "taxpayer.vat_status", "operator": "equals", "value": "小规模纳税人"}, {"fact": "transaction.original_levy_rate", "operator": "equals", "value": 0.03}]}, then={"outcome": "levy_rate", "value": 0.01, "confidence": "deterministic"}, requires=[])
        exclusion = make_rule(rule_id="VAT-PROPERTY-EXCLUSION", priority=200, exclusive_group="vat_levy_rate", when={"fact": "transaction.transaction_type", "operator": "equals", "value": "不动产"}, then={"outcome": "levy_rate_excluded", "value": True, "confidence": "deterministic"}, requires=[])
        bundle = RuleEngine().evaluate_all([one_percent, exclusion], graph, date(2026, 7, 18))
        self.assertEqual(bundle.selected["vat_levy_rate"].rule_id, "VAT-PROPERTY-EXCLUSION")
        self.assertEqual(bundle.selected["vat_levy_rate"].outcome, "levy_rate_excluded")
        self.assertFalse(bundle.conflicts)

    def test_same_priority_exclusive_rules_create_conflict(self):
        graph = make_graph({"transaction.transaction_type": "服务"})
        first = make_rule(rule_id="R1", priority=100, exclusive_group="rate", when={"fact": "transaction.transaction_type", "operator": "equals", "value": "服务"}, then={"outcome": "levy_rate", "value": 0.01}, requires=[])
        second = make_rule(rule_id="R2", priority=100, exclusive_group="rate", when={"fact": "transaction.transaction_type", "operator": "equals", "value": "服务"}, then={"outcome": "levy_rate", "value": 0.03}, requires=[])
        bundle = RuleEngine().evaluate_all([first, second], graph, date(2026, 7, 18))
        self.assertEqual(len(bundle.conflicts), 1)
        self.assertEqual(bundle.conflicts[0].status, RuleEvaluationStatus.CONFLICT)
        self.assertNotIn("rate", bundle.selected)


if __name__ == "__main__": unittest.main()
