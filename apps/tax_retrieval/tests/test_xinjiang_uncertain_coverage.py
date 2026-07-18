import unittest
from pathlib import Path
from types import SimpleNamespace

from apps.tax_retrieval import HybridRetrievalEngine

ROOT = Path(__file__).resolve().parents[3]


class XinjiangUncertainCoverageTests(unittest.TestCase):
    def test_uncertain_local_rule_is_conflict_not_support(self):
        facts = SimpleNamespace(
            description="新疆总分机构增值税汇总核算2026是否仍适用",
            region="CN-XJ",
            business_date="2026-07-18",
            taxpayer_type="企业",
            vat_status="一般纳税人",
            transaction_type="服务",
            amount_period="季度",
            invoice_need="普通发票",
            objective="合规",
            related_party=False,
            cross_border=False,
            historical_tax=False,
            hainan_special_scene=False,
            hs_code="",
        )
        bundle = HybridRetrievalEngine(ROOT).search_bundle(facts, top_k=10)
        self.assertTrue(bundle.support)
        self.assertTrue(any("新疆增值税汇总核算管理办法" in item.path for item in bundle.conflict))
        self.assertFalse(any("新疆增值税汇总核算管理办法" in item.path for item in bundle.support))


if __name__ == "__main__":
    unittest.main()
