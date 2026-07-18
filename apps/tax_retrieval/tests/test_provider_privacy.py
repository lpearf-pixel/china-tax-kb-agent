import unittest
from pathlib import Path
from types import SimpleNamespace

from apps.tax_retrieval import HybridRetrievalEngine


def doc():
    return {"chunk_id":"x","path":"02-条款结构/x.md","heading":"起征点","text":"小规模纳税人起征点","metadata":{"jurisdiction_scope":"CN","evidence_tier":"A","document_status":"effective","tax_types":["增值税"],"provision_id":"P1","title":"起征点"}}


class ProviderPrivacyTests(unittest.TestCase):
    def test_provider_does_not_receive_full_business_description(self):
        captured = []
        class Provider:
            def embed(self, texts):
                captured.extend(texts)
                return [[1.0, 0.0] for _ in texts]
        facts = SimpleNamespace(description="客户甲秘密合同身份证信息", region="CN", business_date="2026-07-18", taxpayer_type="企业", vat_status="小规模纳税人", transaction_type="服务", amount_period="季度", invoice_need="普通发票", objective="合规", related_party=False, cross_border=False, historical_tax=False, hainan_special_scene=False, hs_code="")
        HybridRetrievalEngine(Path("."), docs=[doc()], embedding_provider=Provider()).search_bundle(facts, top_k=2)
        self.assertTrue(captured)
        self.assertNotIn("秘密合同", captured[0])
        self.assertNotIn("身份证", captured[0])
        self.assertIn("main", captured[0])


if __name__ == "__main__":
    unittest.main()
