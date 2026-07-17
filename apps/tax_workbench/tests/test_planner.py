import unittest
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService


ROOT = Path(__file__).resolve().parents[3]


def make_facts(**overrides):
    data = {
        "business_date": "2026-07-17",
        "region": "CN-XJ",
        "taxpayer_type": "企业",
        "vat_status": "小规模纳税人",
        "transaction_type": "服务",
        "amount": "240000",
        "amount_period": "季度",
        "amount_tax_inclusive": False,
        "invoice_need": "普通发票",
        "objective": "合规降负",
        "description": "咨询服务",
    }
    data.update(overrides)
    return TaxFacts.from_dict(data)


class TaxPlanningServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = TaxPlanningService(ROOT)

    def test_xinjiang_quarterly_240k_gets_threshold_preliminary_conclusion(self):
        result = self.service.analyze(make_facts())
        self.assertIn("季度30万元", result.initial_conclusion)
        self.assertFalse(result.human_review_required)
        self.assertGreaterEqual(len(result.evidence), 1)
        self.assertEqual(len(result.schemes), 3)

    def test_small_scale_service_gets_one_percent_direction(self):
        result = self.service.analyze(make_facts(amount="400000", amount_period="季度"))
        combined = " ".join(s.summary for s in result.schemes)
        self.assertIn("1%", combined)

    def test_hainan_ordinary_consulting_does_not_apply_zero_tariff(self):
        result = self.service.analyze(make_facts(region="CN-HI", description="海口软件咨询服务"))
        self.assertIn("普通境内服务", result.regional_application)
        self.assertNotIn("可直接适用零关税", result.initial_conclusion)
        self.assertFalse(result.human_review_required)

    def test_hainan_import_missing_hs_code_requires_human_review(self):
        facts = make_facts(
            region="CN-HI",
            transaction_type="进口货物",
            description="从境外进口生产设备",
            hainan_special_scene=True,
            hs_code="",
            qualified_entity=None,
        )
        result = self.service.analyze(facts)
        self.assertTrue(result.human_review_required)
        self.assertIn("商品 HS 编码", result.missing_facts)
        self.assertTrue(any("不能确定" in risk or "不得" in risk for risk in result.risks))

    def test_related_party_split_signal_requires_review(self):
        result = self.service.analyze(make_facts(related_party=True, description="关联公司拆分销售额"))
        self.assertTrue(result.human_review_required)
        self.assertTrue(any("关联" in risk or "分拆" in risk for risk in result.risks))


if __name__ == "__main__":
    unittest.main()
