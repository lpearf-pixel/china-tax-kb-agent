import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]


def payload(**overrides):
    data = {
        "business_date": "2026-07-19",
        "region": "CN",
        "taxpayer_type": "企业",
        "vat_status": "小规模纳税人",
        "transaction_type": "服务",
        "amount": "400000",
        "total_sales_same_period": "400000",
        "amount_period": "季度",
        "invoice_need": "普通发票",
        "objective": "综合税负",
        "description": "居民公司年度税务方案",
        "original_levy_rate": "0.03",
        "entity_form": "公司制企业",
        "cit_resident_status": "居民企业",
        "cit_accounting_profit": "1000000",
        "cit_adjustment_increase": "0",
        "cit_adjustment_decrease": "0",
        "cit_loss_carryforward": "0",
        "cit_tax_credit": "0",
        "cit_prepaid_tax": "0",
        "cit_employee_count_avg": "20",
        "cit_asset_total_avg": "10000000",
        "cit_restricted_industry": False,
    }
    data.update(overrides)
    return TaxFacts.from_dict(data)


class MultiTaxWorkbenchTests(unittest.TestCase):
    def service(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return TaxPlanningService(ROOT, case_root=Path(self.temp.name))

    def test_legacy_request_remains_vat_only(self):
        result = self.service().analyze(payload(requested_tax_types=None))
        self.assertEqual({row["tax_type"] for row in result.calculations}, {"增值税"})

    def test_cit_only_request_returns_five_percent_small_profit_tax(self):
        result = self.service().analyze(payload(requested_tax_types=["企业所得税"]))
        cit = next(row for row in result.calculations if row["tax_type"] == "企业所得税")
        self.assertEqual(Decimal(cit["tax_amount"]["value"]), Decimal("50000.00"))
        self.assertEqual(set(result.schemes[0].tax_breakdown), {"企业所得税"})

    def test_combined_request_returns_tax_breakdown_and_total(self):
        result = self.service().analyze(payload(requested_tax_types=["增值税", "企业所得税"]))
        self.assertEqual({row["tax_type"] for row in result.calculations}, {"增值税", "企业所得税"})
        scheme = result.schemes[0]
        self.assertIn("增值税", scheme.tax_breakdown)
        self.assertIn("企业所得税", scheme.tax_breakdown)
        self.assertEqual(Decimal(scheme.estimated_tax), sum(scheme.tax_breakdown.values()))

    def test_2028_uses_general_cit_rate_not_expired_small_profit_rule(self):
        result = self.service().analyze(payload(business_date="2028-01-01", requested_tax_types=["企业所得税"]))
        cit = next(row for row in result.calculations if row["tax_type"] == "企业所得税")
        self.assertEqual(Decimal(cit["tax_amount"]["value"]), Decimal("250000.00"))
        self.assertNotIn("CIT-SMALL-LOW-PROFIT-RATE-2023-2027", cit["rule_ids"])


if __name__ == "__main__":
    unittest.main()
