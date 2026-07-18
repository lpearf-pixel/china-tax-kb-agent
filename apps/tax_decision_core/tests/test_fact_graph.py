from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from apps.tax_decision_core.domain import CaseState, FactStatus
from apps.tax_decision_core.fact_graph import FactGraphService, MissingFact
from apps.tax_decision_core.storage import CaseStorage


class FactGraphServiceTests(unittest.TestCase):
    def make_payload(self):
        return {
            "case_id": "case-graph-001",
            "nodes": [
                {"node_id": "party-seller", "node_type": "Party", "name": "新疆咨询公司"},
                {"node_id": "party-buyer", "node_type": "Party", "name": "客户"},
                {"node_id": "tx-1", "node_type": "Transaction", "transaction_type": "服务"},
                {"node_id": "contract-1", "node_type": "Contract", "title": "咨询合同"},
                {"node_id": "invoice-1", "node_type": "InvoiceFlow", "invoice_type": "普通发票"},
                {"node_id": "cash-1", "node_type": "CashFlow", "purpose": "咨询费"},
                {"node_id": "service-1", "node_type": "ServiceFlow", "place": "新疆"},
            ],
            "edges": [
                {"source": "party-seller", "relation": "signs", "target": "contract-1"},
                {"source": "contract-1", "relation": "governs", "target": "tx-1"},
                {"source": "tx-1", "relation": "has_invoice_flow", "target": "invoice-1"},
                {"source": "tx-1", "relation": "has_cash_flow", "target": "cash-1"},
                {"source": "tx-1", "relation": "has_service_flow", "target": "service-1"},
            ],
            "facts": {
                "transaction.business_date": {"value": "2026-07-18", "source": "contract"},
                "transaction.sales_amount": {"value": Decimal("240000"), "source": "user"},
                "invoice.need_special_invoice": {"value": False, "source": "user"},
                "taxpayer.vat_status": {"value": "小规模纳税人", "source": "registration"},
            },
        }

    def test_create_case_persists_graph_and_validates_nodes_edges(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            case = service.create_case(self.make_payload())
            graph = service.load_graph(case.case_id)

            self.assertEqual(case.state, CaseState.FACTS_PENDING_CONFIRMATION)
            self.assertEqual(graph.nodes["tx-1"]["node_type"], "Transaction")
            self.assertEqual(len(graph.edges), 5)
            self.assertEqual(graph.facts["transaction.sales_amount"].current.value, Decimal("240000"))

    def test_rejects_unknown_node_and_relation_types(self):
        with tempfile.TemporaryDirectory() as td:
            service = FactGraphService(CaseStorage(Path(td)))
            payload = self.make_payload()
            payload["nodes"].append({"node_id": "x", "node_type": "ShellCommand"})
            with self.assertRaises(ValueError):
                service.create_case(payload)

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
            self.assertEqual(set(impact.affected_nodes), {"evidence", "rules", "calculation", "scenarios"})

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


if __name__ == "__main__":
    unittest.main()
