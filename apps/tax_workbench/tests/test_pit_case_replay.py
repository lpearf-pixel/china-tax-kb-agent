import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]


class PitCaseReplayTests(unittest.TestCase):
    def facts(self):
        return TaxFacts.from_dict({
            "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "个体工商户",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "1000000",
            "amount_period": "年度", "invoice_need": "普通发票", "objective": "个人所得税",
            "description": "个体工商户经营所得", "requested_tax_types": ["个人所得税"],
            "pit_income_category": "经营所得", "pit_resident_status": "居民个人",
            "pit_taxpayer_role": "个体工商户业主", "pit_business_taxable_income": "1000000",
            "pit_business_other_tax_reduction": "0", "pit_business_prepaid_tax": "0",
            "pit_multiple_business_sources": False,
        })

    def test_pit_fact_revision_replays_full_decision_chain(self):
        with tempfile.TemporaryDirectory() as td:
            service = TaxPlanningService(ROOT, case_root=Path(td))
            created = service.create_case(self.facts())
            impact = service.revise_case_fact(
                created.case_id,
                "pit.business_taxable_income",
                "30000",
                "owner",
            )
            self.assertEqual(
                set(impact["affected_nodes"]),
                {"issues", "evidence", "rules", "calculation", "scenarios", "human_review"},
            )
            refreshed = service.analyze_case(created.case_id)
            pit = next(row for row in refreshed.calculations if row["tax_type"] == "个人所得税")
            self.assertEqual(Decimal(pit["tax_amount"]["value"]), Decimal("750.00"))


if __name__ == "__main__":
    unittest.main()
