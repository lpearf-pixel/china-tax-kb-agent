from __future__ import annotations

import unittest
from decimal import Decimal

from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts


class V6AdapterTests(unittest.TestCase):
    def facts(self):
        return TaxFacts.from_dict(
            {
                "business_date": "2026-07-17",
                "region": "CN-HI",
                "taxpayer_type": "企业",
                "vat_status": "小规模纳税人",
                "transaction_type": "进口货物",
                "amount": "1010000",
                "amount_period": "单次",
                "amount_tax_inclusive": True,
                "invoice_need": "专用发票",
                "objective": "海南政策预审",
                "description": "进口生产设备",
                "cross_border": True,
                "hainan_special_scene": True,
                "hs_code": "8471.30",
                "qualified_entity": True,
                "flow": "一线进口",
                "use": "生产自用",
                "original_levy_rate": "0.03",
            }
        )

    def test_v6_facts_round_trip_through_single_transaction_graph(self):
        adapter = V6Adapter()
        case, graph = adapter.to_v7(self.facts(), "case-adapter")
        self.assertEqual(case.case_id, "case-adapter")
        self.assertEqual(
            graph.facts["transaction.sales_amount"].current.value,
            Decimal("1010000"),
        )
        self.assertEqual(
            graph.facts["goods_flow.flow"].current.value,
            "一线进口",
        )

        restored = adapter.from_graph(graph)
        self.assertEqual(restored.region, "CN-HI")
        self.assertEqual(restored.transaction_type, "进口货物")
        self.assertEqual(restored.amount, Decimal("1010000"))
        self.assertEqual(restored.extra["flow"], "一线进口")
        self.assertEqual(restored.extra["use"], "生产自用")


if __name__ == "__main__":
    unittest.main()
