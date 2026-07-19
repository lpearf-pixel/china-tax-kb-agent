import unittest
from decimal import Decimal

from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts


class CitFactAdapterTests(unittest.TestCase):
    def test_legacy_request_defaults_to_vat_only(self):
        facts = TaxFacts.from_dict({
            "business_date": "2026-07-19",
            "region": "CN",
            "taxpayer_type": "企业",
            "vat_status": "小规模纳税人",
            "transaction_type": "服务",
            "amount": "100000",
            "amount_period": "季度",
            "invoice_need": "普通发票",
            "objective": "合规",
            "description": "咨询服务",
        })
        self.assertEqual(facts.requested_tax_types, ["增值税"])

    def test_multitax_fields_are_decimal_and_mapped_to_graph(self):
        facts = TaxFacts.from_dict({
            "business_date": "2026-07-19",
            "region": "CN",
            "taxpayer_type": "企业",
            "vat_status": "一般纳税人",
            "transaction_type": "服务",
            "amount": "1000000",
            "amount_period": "年度",
            "invoice_need": "专用发票",
            "objective": "综合税负",
            "description": "居民公司年度税务测算",
            "requested_tax_types": ["增值税", "企业所得税"],
            "entity_form": "公司制企业",
            "cit_resident_status": "居民企业",
            "cit_accounting_profit": "1000000",
            "cit_adjustment_increase": "100000",
            "cit_adjustment_decrease": "50000",
            "cit_loss_carryforward": "20000",
            "cit_employee_count_avg": "20",
            "cit_asset_total_avg": "10000000",
            "cit_restricted_industry": False,
        })
        self.assertEqual(facts.cit_accounting_profit, Decimal("1000000"))
        _, graph = V6Adapter().to_v7(facts, "case-cit-adapter")
        self.assertEqual(graph.facts["cit.accounting_profit"].current.value, Decimal("1000000"))
        self.assertEqual(graph.facts["cit.entity_form"].current.value, "公司制企业")
        self.assertEqual(graph.facts["case.requested_tax_types"].current.value, ["增值税", "企业所得税"])


if __name__ == "__main__":
    unittest.main()
