import json
import unittest
from pathlib import Path

from apps.tax_retrieval import HybridRetrievalEngine
from apps.tax_workbench.models import TaxFacts

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "11-问题测试集" / "v7_1_retrieval_cases.jsonl"


class RetrievalCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = HybridRetrievalEngine(ROOT)
        cls.cases = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_corpus_has_thirty_unique_cases(self):
        self.assertGreaterEqual(len(self.cases), 30)
        ids = [item["id"] for item in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_declared_retrieval_expectations(self):
        for item in self.cases:
            with self.subTest(case_id=item["id"]):
                bundle = self.engine.search_bundle(TaxFacts.from_dict(item["facts"]), top_k=8)
                groups = bundle.grouped()
                expected = item["expected"]
                for role in expected.get("roles", []):
                    self.assertTrue(groups[role], f"missing role {role}")
                for role in ("support", "limitation", "exclusion", "historical", "local"):
                    key = f"{role}_contains"
                    if expected.get(key):
                        self.assertTrue(any(expected[key] in row.path for row in groups[role]), f"{role} missing {expected[key]}")
                if expected.get("support_required"):
                    self.assertTrue(groups["support"])
                if expected.get("limitation_required"):
                    self.assertTrue(groups["limitation"])
                if expected.get("no_historical"):
                    self.assertFalse(groups["historical"])
                if expected.get("local_scope"):
                    self.assertTrue(any(row.jurisdiction_scope == expected["local_scope"] for row in groups["local"]))
                if expected.get("forbid_any_contains"):
                    self.assertFalse(any(expected["forbid_any_contains"] in row.path for rows in groups.values() for row in rows))
                if expected.get("trace_required"):
                    self.assertIsNotNone(bundle.trace)
                    self.assertTrue(bundle.trace.query_stats)
                if expected.get("trace_role"):
                    self.assertTrue(any(query.get("role") == expected["trace_role"] for query in bundle.trace.plan.get("queries", [])))
                for rows in groups.values():
                    for row in rows:
                        self.assertEqual(row.evidence_tier, "A")


if __name__ == "__main__":
    unittest.main()
