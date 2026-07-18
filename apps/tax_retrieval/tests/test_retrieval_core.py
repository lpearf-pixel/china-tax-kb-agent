import unittest
from pathlib import Path
from types import SimpleNamespace

from apps.tax_retrieval.classifier import EvidenceClassifier
from apps.tax_retrieval.engine import HybridRetrievalEngine
from apps.tax_retrieval.fusion import rrf_fuse
from apps.tax_retrieval.models import QueryPlan, QuerySpec, RetrievalCandidate
from apps.tax_retrieval.query_planner import QueryPlanner
from apps.tax_retrieval.reranker import DeterministicReranker
from apps.tax_retrieval.vector_index import HashingVectorIndex, HashingVectorizer
from apps.tax_retrieval.versioning import VersionResolver


def candidate(cid, text, path="02-条款结构/x.md", **meta):
    return RetrievalCandidate(cid, path, cid, meta.get("title", "条款"), text, meta)


def doc(cid, path, text, **meta):
    defaults = dict(jurisdiction_scope="CN", evidence_tier="A", document_status="effective", tax_types=["增值税"], title=path)
    defaults.update(meta)
    return {"chunk_id": cid, "path": path, "heading": defaults["title"], "text": text, "metadata": defaults}


class RetrievalCoreTests(unittest.TestCase):
    def facts(self, **changes):
        payload = dict(description="新疆咨询服务", region="CN-XJ", business_date="2026-07-18", taxpayer_type="企业", vat_status="小规模纳税人", transaction_type="服务", amount_period="季度", invoice_need="普通发票", objective="合规降负", related_party=False, cross_border=False, historical_tax=False, hainan_special_scene=False, hs_code="")
        payload.update(changes)
        return SimpleNamespace(**payload)

    def test_xinjiang_plan_contains_six_roles(self):
        plan = QueryPlanner().plan(self.facts())
        self.assertEqual({q.role for q in plan.queries}, {"main", "eligibility", "limitation", "exclusion", "version", "local"})
        self.assertTrue(all(len(q.text) <= 500 for q in plan.queries))

    def test_hainan_import_contains_gate_terms(self):
        plan = QueryPlanner().plan(self.facts(region="CN-HI", transaction_type="进口货物", hainan_special_scene=True, hs_code="8471"))
        text = " ".join(q.text for q in plan.queries)
        for term in ("享惠主体", "HS编码", "一线", "二线", "普通税制基线", "人工复核"):
            self.assertIn(term, text)
        self.assertIsNone(plan.tax_type)

    def test_historical_question_expands_statuses(self):
        plan = QueryPlanner().plan(self.facts(description="2025年当时适用什么旧规", historical_tax=True))
        self.assertTrue(plan.historical_requested)
        self.assertIn("repealed", next(q for q in plan.queries if q.role == "version").statuses)

    def test_same_text_cosine_is_one_and_empty_is_safe(self):
        vectorizer = HashingVectorizer(128)
        vector = vectorizer.transform("小规模纳税人起征点")
        self.assertAlmostEqual(vectorizer.cosine(vector, vector), 1.0)
        self.assertEqual(sum(vectorizer.transform("")), 0.0)

    def test_tax_synonym_is_above_unrelated_text(self):
        docs = [doc("rate", "02-条款结构/rate.md", "小规模纳税人适用1%征收率"), doc("deed", "02-条款结构/deed.md", "房屋权属转移契税计税依据")]
        self.assertEqual(HashingVectorIndex(docs, 256).search("减按百分之一征收增值税", 2)[0][0]["chunk_id"], "rate")

    def test_rrf_rewards_multi_route_candidate(self):
        scores = rrf_fuse([["a", "b"], ["a", "c"]])
        self.assertGreater(scores["a"], scores["b"])

    def test_classifier_roles(self):
        classifier = EvidenceClassifier()
        self.assertEqual(classifier.classify(candidate("e", "除销售出租不动产外，不适用本项"), "CN")[0], "exclusion")
        self.assertEqual(classifier.classify(candidate("l", "必须核验同一计税期间全部应税交易"), "CN")[0], "limitation")
        self.assertEqual(classifier.classify(candidate("h", "旧规定", document_status="repealed"), "CN")[0], "historical")
        self.assertEqual(classifier.classify(candidate("x", "新疆执行口径", jurisdiction_scope="CN-XJ"), "CN-XJ")[0], "local")

    def test_version_resolver_selects_valid_latest_version(self):
        old = candidate("old", "旧条款", provision_id="P1", provision_valid_from="2023-01-01", provision_valid_to="2025-12-31")
        new = candidate("new", "新条款", provision_id="P1", provision_valid_from="2026-01-01")
        self.assertEqual([row.candidate_id for row in VersionResolver().resolve([old, new], "2026-07-18", False)], ["new"])

    def test_reranker_prefers_clause_over_case(self):
        plan = QueryPlan("CN", "2026-07-18", "增值税", [QuerySpec("q", "main", "小规模起征点")])
        clause = candidate("clause", "小规模起征点", path="02-条款结构/起征点.md", title="小规模起征点")
        case = candidate("case", "小规模起征点", path="08-税务规划案例/案例.md", title="案例")
        for row in (clause, case):
            row.rrf_score = 0.1
            row.query_roles.add("main")
        self.assertEqual(DeterministicReranker().rank([case, clause], plan)[0].candidate_id, "clause")

    def test_bundle_separates_roles(self):
        docs = [
            doc("support", "02-条款结构/support.md", "小规模纳税人季度销售额30万元起征点", provision_id="P-S"),
            doc("limit", "02-条款结构/limit.md", "必须核验同一计税期间全部应税交易", provision_id="P-L"),
            doc("exclude", "02-条款结构/exclude.md", "销售出租不动产不适用1%政策", provision_id="P-E"),
            doc("local", "02-条款结构/local.md", "新疆执行全国增值税规则", provision_id="P-X", jurisdiction_scope="CN-XJ"),
        ]
        bundle = HybridRetrievalEngine(Path("."), docs=docs).search_bundle(self.facts(), top_k=4)
        self.assertTrue(bundle.support and bundle.limitation and bundle.exclusion and bundle.local)

    def test_relation_expansion_cannot_bypass_a_tier_gate(self):
        docs = [doc("legal", "02-条款结构/legal.md", "起征点条款", document_id="D1", provision_id="P1"), doc("case", "08-税务规划案例/case.md", "案例起征点", document_id="D1", provision_id="P2", evidence_tier="")]
        bundle = HybridRetrievalEngine(Path("."), docs=docs).search_bundle(self.facts(), top_k=5)
        paths = {item.path for rows in bundle.grouped().values() for item in rows}
        self.assertNotIn("08-税务规划案例/case.md", paths)

    def test_provider_failure_falls_back_and_is_traced(self):
        class BrokenProvider:
            def embed(self, texts):
                raise RuntimeError("offline")
        bundle = HybridRetrievalEngine(Path("."), docs=[doc("support", "02-条款结构/support.md", "小规模纳税人起征点", provision_id="P1")], embedding_provider=BrokenProvider()).search_bundle(self.facts(), top_k=2)
        self.assertEqual(bundle.trace.provider, "local_hashing_fallback")
        self.assertTrue(bundle.trace.provider_errors)
