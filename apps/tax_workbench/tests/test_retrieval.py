import json
import tempfile
import unittest
from pathlib import Path

from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.retrieval import EvidenceRetriever


class EvidenceRetrieverTests(unittest.TestCase):
    def make_vault(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        chunks = root / "90-工具/output/chunks.jsonl"
        chunks.parent.mkdir(parents=True)
        docs = [
            {
                "path": "02-条款结构/全国.md",
                "heading": "全国条款",
                "text": "小规模纳税人季度销售额30万元起征点",
                "metadata": {"jurisdiction_scope": "CN", "evidence_tier": "A", "provision_status": "effective", "tax_types": ["增值税"], "document_number": "全国1号", "title": "全国规则"},
            },
            {
                "path": "02-条款结构/新疆.md",
                "heading": "新疆条款",
                "text": "新疆地方办税补充口径",
                "metadata": {"jurisdiction_scope": "CN-XJ", "evidence_tier": "A", "provision_status": "effective", "tax_types": ["增值税"], "title": "新疆规则"},
            },
            {
                "path": "02-条款结构/海南.md",
                "heading": "海南条款",
                "text": "海南进口零关税享惠主体 HS编码",
                "metadata": {"jurisdiction_scope": "CN-HI", "evidence_tier": "A", "provision_status": "effective", "tax_types": ["增值税"], "title": "海南规则"},
            },
            {
                "path": "03-概念解释/解读.md",
                "heading": "解读",
                "text": "季度30万元通俗解释",
                "metadata": {"jurisdiction_scope": "CN", "evidence_tier": "B", "document_status": "effective", "tax_types": ["增值税"], "title": "解读"},
            },
            {
                "path": "02-条款结构/过期.md",
                "heading": "旧条款",
                "text": "旧优惠",
                "metadata": {"jurisdiction_scope": "CN", "evidence_tier": "A", "provision_status": "effective", "provision_valid_to": "2025-12-31", "tax_types": ["增值税"], "title": "旧规则"},
            },
        ]
        chunks.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in docs), encoding="utf-8")
        return td, root

    def facts(self, region="CN-XJ", description="季度销售额24万元咨询服务"):
        return TaxFacts.from_dict({
            "business_date": "2026-07-17", "region": region, "taxpayer_type": "企业",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "240000",
            "amount_period": "季度", "invoice_need": "普通发票", "objective": "合规", "description": description,
        })

    def test_xinjiang_keeps_national_and_xinjiang_not_hainan(self):
        td, root = self.make_vault()
        self.addCleanup(td.cleanup)
        items = EvidenceRetriever(root).search(self.facts("CN-XJ"), top_k=10)
        paths = {item.path for item in items}
        self.assertIn("02-条款结构/全国.md", paths)
        self.assertIn("02-条款结构/新疆.md", paths)
        self.assertNotIn("02-条款结构/海南.md", paths)

    def test_hainan_keeps_national_and_hainan_and_only_a_tier(self):
        td, root = self.make_vault()
        self.addCleanup(td.cleanup)
        items = EvidenceRetriever(root).search(self.facts("CN-HI", "进口零关税HS编码"), top_k=10)
        paths = {item.path for item in items}
        self.assertIn("02-条款结构/全国.md", paths)
        self.assertIn("02-条款结构/海南.md", paths)
        self.assertNotIn("03-概念解释/解读.md", paths)
        self.assertNotIn("02-条款结构/新疆.md", paths)

    def test_date_filter_excludes_expired_provision(self):
        td, root = self.make_vault()
        self.addCleanup(td.cleanup)
        items = EvidenceRetriever(root).search(self.facts(), top_k=10)
        self.assertNotIn("02-条款结构/过期.md", {item.path for item in items})


if __name__ == "__main__":
    unittest.main()
