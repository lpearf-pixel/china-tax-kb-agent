from __future__ import annotations

import unittest

from apps.tax_decision_core.fact_graph import FactGraphService


class FactImpactRoutingTests(unittest.TestCase):
    def test_related_party_and_split_rebuild_issue_and_review_layers(self):
        for fact_id in ("transaction.related_party", "transaction.split_signal"):
            with self.subTest(fact_id=fact_id):
                affected = set(FactGraphService._affected_nodes(fact_id))
                self.assertTrue({"issues", "rules", "calculation", "scenarios", "human_review"} <= affected)

    def test_transaction_type_and_cross_border_rebuild_evidence(self):
        for fact_id in ("transaction.transaction_type", "transaction.cross_border"):
            with self.subTest(fact_id=fact_id):
                affected = set(FactGraphService._affected_nodes(fact_id))
                self.assertTrue({"issues", "evidence", "rules", "calculation", "scenarios", "human_review"} <= affected)

    def test_hainan_and_goods_facts_rebuild_special_policy_gate(self):
        for fact_id in ("hainan.qualified_entity", "goods_flow.hs_code", "goods_flow.flow"):
            with self.subTest(fact_id=fact_id):
                affected = set(FactGraphService._affected_nodes(fact_id))
                self.assertIn("evidence", affected)
                self.assertIn("human_review", affected)


if __name__ == "__main__":
    unittest.main()
