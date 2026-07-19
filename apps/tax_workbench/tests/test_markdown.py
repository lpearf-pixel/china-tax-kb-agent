import tempfile
import unittest
from pathlib import Path

from apps.tax_workbench.markdown import render_markdown, save_session
from apps.tax_workbench.models import EvidenceItem, PlanningResult, SchemeOption, TaxFacts


class MarkdownTests(unittest.TestCase):
    def result(self):
        return PlanningResult(
            initial_conclusion="初步结论",
            applicable_conditions=["地区：新疆"],
            evidence=[EvidenceItem(path="02-条款.md", title="起征点条款", document_number="2026年第10号", article="第一条", excerpt="季度30万元", score=1.2)],
            explanation="通俗解释",
            regional_application="新疆适用全国底座",
            schemes=[SchemeOption(name="方案A", summary="合规基线", actions=["核对销售额"], benefits=["风险低"], risks=["需核验"], required_documents=["申报表"])],
            risks=["风险提示"],
            missing_facts=["专票需求"],
            human_review_required=False,
            kb_version="KB-TEST",
            verified_at="2026-07-17",
        )

    def facts(self):
        return TaxFacts.from_dict({
            "business_date": "2026-07-17", "region": "CN-XJ", "taxpayer_type": "企业",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "240000",
            "amount_period": "季度", "invoice_need": "普通发票", "objective": "合规", "description": "咨询",
        })

    def test_render_contains_required_sections_and_citation(self):
        text = render_markdown(self.facts(), self.result())
        for heading in ("初步结论", "适用前提", "法规证据包", "税务方案", "风险与待确认事项", "信息时效"):
            self.assertIn(heading, text)
        self.assertIn("2026年第10号", text)
        self.assertIn("KB-TEST", text)

    def test_save_session_creates_unique_markdown_under_workbench(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = save_session(root, self.facts(), self.result())
            second = save_session(root, self.facts(), self.result())
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertIn("16-交互工作台/会话记录", first.as_posix())


if __name__ == "__main__":
    unittest.main()
