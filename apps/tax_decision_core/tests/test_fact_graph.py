import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from apps.tax_decision_core.domain import FactStatus
from apps.tax_decision_core.fact_graph import FactGraphService, MissingFact
from apps.tax_decision_core.storage import CaseStorage


class FactGraphServiceTests(unittest.TestCase):
    @staticmethod
    def make_payload():
        return {
            "case": {
                "case_id": "case-facts",
                "state": "draft",
                "kb_version": "KB-test",
                "rule_set_version": "rules-test",
                "facts_version": 1,
                "created_at": "2026-07-18T00:00:00+00:00",
                "updated_at": "2026-07-18T00:00:00+00:00",
            },
            "graph": {
                "version": 1,
                "nodes": {
                    "party-seller": {"node_id": "party-seller", "node_type": "Party", "name": "Seller"},
                    "party-buyer": {"node_id": "party-buyer", "node_type": "Party", "name": "Buyer"},
                    "tx-1": {"node_id": "tx-1", "node_type": "Transaction", "transaction_type": "服务"},
                },
                "edges": [
                    {"source": "party-seller", "relation": "executes", "target": "tx-1"},
                    {"source": "tx-1", "relation": "counterparty", "target": "party-buyer"},
                ],
                "facts": {
                    "transaction.sales_amount": {
                        "fact_id": "transaction.sales_amount",
                        "versions": [
                            {
                                "fact_id": "transaction.sales_amount",
                                "version": 1,
                                "value": {"__type__": "decimal", "value": "100000"},
                                "status": "candidate",
                                "source": "user",
                                "captured_at": "2026-07-18T00:00:00+00:00",
                                "captured_by": "user",
                                "valid_from": None,
                                "valid_to": None,
                                "sensitive_level": "internal",
                            }
                        ],
                    },
                    "invoice.need_special_invoice": {
                        "fact_id": "invoice.need_special_invoice",
                        "versions": [
                            {
                                "fact_id": "invoice.need_special_invoice",
                                "version": 1,
                                "value": False,
                                "status": "confirmed",
                                "source": "user",
                                "captured_at": "2026-07-18T00:00:00+00:00",
                                "captured_by": "user",
                                "valid_from": None,
                                "valid_to": None,
                                "sensitive_level": "internal",
                            }
                        ],
                    },
                },
            },
        }

    def test_create_case_persists_graph_and_validates_nodes_edges(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            case = service.create_case(self.make_payload())
            graph = service.load_graph(case.case_id)
            self.assertEqual(graph.version, 1)
            self.assertIn("party-seller", graph.nodes)

            payload = self.make_payload()
            payload["edges"].append({"source": "tx-1", "relation": "executes", "target": "party-buyer"})
            with self.assertRaises(ValueError):
                service.create_case(payload)

    def test_confirm_and_revise_fact_create_versions_and_impact_sets(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            case = service.create_case(self.make_payload())

            confirmed = service.confirm_fact(case.case_id, "transaction.sales_amount", Decimal("240000"), "owner")
            self.assertEqual(confirmed.status, FactStatus.CONFIRMED)
            self.assertEqual(confirmed.version, 2)

            impact = service.revise_fact(case.case_id, "invoice.need_special_invoice", True, "owner")
            self.assertEqual(impact.new_version, 2)
            self.assertEqual(set(impact.affected_nodes), {"rules", "calculation", "scenarios"})

            impact = service.revise_fact(case.case_id, "transaction.business_date", date(2026, 8, 1), "owner")
            self.assertEqual(set(impact.affected_nodes), {"issues", "evidence", "rules", "calculation", "scenarios"})

            graph = service.load_graph(case.case_id)
            versions = graph.facts["invoice.need_special_invoice"].versions
            self.assertEqual(versions[0].status, FactStatus.SUPERSEDED)
            self.assertEqual(versions[-1].value, True)

    def test_missing_fact_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            case = service.create_case(self.make_payload())
            graph = service.load_graph(case.case_id)

            missing = service.get_value(graph, "goods_flow.hs_code")
            self.assertIsInstance(missing, MissingFact)
            self.assertEqual(missing.fact_id, "goods_flow.hs_code")

    def test_rejects_unknown_node_and_relation_types(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            payload = self.make_payload()
            payload["graph"]["nodes"]["bad"] = {"node_id": "bad", "node_type": "Unknown"}
            with self.assertRaises(ValueError):
                service.create_case(payload)

            payload = self.make_payload()
            payload["graph"]["edges"].append({"source": "party-seller", "relation": "unknown", "target": "tx-1"})
            with self.assertRaises(ValueError):
                service.create_case(payload)


if __name__ == "__main__":
    unittest.main()
