import unittest
from pathlib import Path

from apps.tax_retrieval import HybridRetrievalEngine
from apps.tax_workbench.models import PlanningResult, SchemeOption, TaxFacts
from apps.tax_workbench.retrieval import EvidenceRetriever


def make_doc(cid, path, text, **metadata):
    base = {"jurisdiction_scope":"CN","evidence_tier":"A","document_status":"effective","tax_types":["增值税"],"title":path}
    base.update(metadata)
    return {"chunk_id":cid,"path":path,"heading":base["title"],"text":text,"metadata":base}


class WorkbenchRetrievalContractTests(unittest.TestCase):
    def facts(self):
        return TaxFacts.from_dict({"business_date":"2026-07-18","region":"CN-XJ","taxpayer_type":"企业","vat_status":"小规模纳税人","transaction_type":"服务","amount":"240000","amount_period":"季度","invoice_need":"普通发票","objective":"合规","description":"新疆咨询服务"})

    def test_legacy_search_returns_a_tier_evidence(self):
        rows = EvidenceRetriever(Path("."), engine=HybridRetrievalEngine(Path("."), docs=[make_doc("s","02-条款结构/s.md","小规模纳税人季度30万元起征点",provision_id="P1")])).search(self.facts(),2)
        self.assertTrue(rows)
        self.assertEqual(rows[0].evidence_tier,"A")
        self.assertTrue(rows[0].score_breakdown)

    def test_legacy_search_fails_closed_without_support(self):
        rows = EvidenceRetriever(Path("."), engine=HybridRetrievalEngine(Path("."), docs=[make_doc("e","02-条款结构/e.md","销售出租不动产不适用1%",provision_id="P2")])).search(self.facts(),3)
        self.assertEqual(rows,[])

    def test_result_exposes_groups_and_top_level_trace(self):
        docs=[make_doc("s","02-条款结构/s.md","小规模纳税人季度30万元起征点",provision_id="P1"),make_doc("e","02-条款结构/e.md","销售出租不动产不适用1%",provision_id="P2")]
        evidence=EvidenceRetriever(Path("."),engine=HybridRetrievalEngine(Path("."),docs=docs)).search(self.facts(),3)
        payload=PlanningResult("结论",evidence=evidence,schemes=[SchemeOption("方案","说明")]).to_dict()
        self.assertTrue(payload["evidence_groups"]["support"])
        self.assertTrue(payload["evidence_groups"]["exclusion"])
        self.assertIn("plan",payload["retrieval_trace"])


if __name__ == "__main__":
    unittest.main()
