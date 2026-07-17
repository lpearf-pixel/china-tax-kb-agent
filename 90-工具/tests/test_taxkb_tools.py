import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from taxkb_core import (
    build_reverse_link_graph,
    chunk_markdown,
    filter_docs,
    parse_frontmatter,
    resolve_wikilink,
    select_note_for_profile,
)


class V5ProfileTests(unittest.TestCase):
    def test_legal_profile_uses_v5_knowledge_layers(self):
        self.assertTrue(select_note_for_profile("01-法规原文/国家/增值税/法.md", "legal"))
        self.assertTrue(select_note_for_profile("02-条款结构/增值税/条款.md", "legal"))
        self.assertTrue(select_note_for_profile("07-政策效力与关系/修改关系/关系.md", "legal"))
        self.assertFalse(select_note_for_profile("11-问题测试集/最近评测报告.md", "legal"))
        self.assertFalse(select_note_for_profile("08-税务规划案例/案例.md", "legal"))

    def test_full_profile_includes_concepts_scenarios_and_workflow(self):
        for rel in (
            "03-概念解释/小规模纳税人.md",
            "04-税种知识/增值税/新疆适用地图.md",
            "05-纳税人类型/自然人.md",
            "06-业务场景/小规模纳税人起征点.md",
            "13-Workflow/税务问答十四节点Workflow.md",
            "14-Agent提示词/系统总提示词.md",
        ):
            self.assertTrue(select_note_for_profile(rel, "full"), rel)


class MetadataFilterTests(unittest.TestCase):
    def test_hainan_query_keeps_national_and_hainan_but_not_xinjiang(self):
        docs = [
            {"path": "national", "metadata": {"jurisdiction_scope": "CN"}},
            {"path": "hainan", "metadata": {"jurisdiction_scope": "CN-HI"}},
            {"path": "xinjiang", "metadata": {"jurisdiction_scope": "CN-XJ"}},
        ]
        kept = filter_docs(docs, jurisdiction="CN-HI")
        self.assertEqual([d["path"] for d in kept], ["national", "hainan"])

    def test_excludes_repealed_and_pending_review_by_default(self):
        docs = [
            {"path": "effective", "metadata": {"provision_status": "effective"}},
            {"path": "repealed", "metadata": {"provision_status": "repealed"}},
            {"path": "pending", "metadata": {"provision_status": "pending_review"}},
        ]
        kept = filter_docs(docs)
        self.assertEqual([d["path"] for d in kept], ["effective"])

    def test_can_request_historical_repealed_material(self):
        docs = [
            {"path": "effective", "metadata": {"document_status": "effective"}},
            {"path": "repealed", "metadata": {"document_status": "repealed"}},
        ]
        kept = filter_docs(docs, statuses={"effective", "repealed"})
        self.assertEqual([d["path"] for d in kept], ["effective", "repealed"])

    def test_evidence_tier_filter_only_keeps_direct_legal_evidence(self):
        docs = [
            {"path": "law", "metadata": {"evidence_tier": "A"}},
            {"path": "interpretation", "metadata": {"evidence_tier": "B"}},
            {"path": "qa", "metadata": {"evidence_tier": "C"}},
        ]
        kept = filter_docs(docs, evidence_tiers={"A"})
        self.assertEqual([d["path"] for d in kept], ["law"])

    def test_valid_on_uses_provision_dates_before_document_dates(self):
        docs = [
            {
                "path": "article",
                "metadata": {
                    "effective_date": "2020-01-01",
                    "provision_valid_from": "2026-01-01",
                    "provision_valid_to": "2027-12-31",
                    "provision_status": "effective",
                },
            }
        ]
        self.assertEqual(filter_docs(docs, valid_on="2025-12-31"), [])
        self.assertEqual(len(filter_docs(docs, valid_on="2026-07-17")), 1)


class SourceDiscoveryTests(unittest.TestCase):
    def test_discovers_v5_law_source_urls(self):
        from taxkb_update import discover_note_sources

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            note = root / "01-法规原文" / "海南" / "政策.md"
            note.parent.mkdir(parents=True)
            note.write_text(
                """---
title: 海南政策
source_url: https://fgk.chinatax.gov.cn/example
jurisdiction_scope: CN-HI
document_status: effective
---
# 政策
""",
                encoding="utf-8",
            )
            sources = discover_note_sources(root)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["note_path"], "01-法规原文/海南/政策.md")


class FrontmatterAndLinkTests(unittest.TestCase):
    def test_parses_lists_and_resolves_v5_wikilinks(self):
        text = """---
title: 测试
related_provisions:
  - VAT-LAW-A9
  - VAT-N10-A1
---
正文
"""
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["related_provisions"], ["VAT-LAW-A9", "VAT-N10-A1"])
        self.assertIn("正文", body)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "02-条款结构" / "增值税" / "条款.md"
            target.parent.mkdir(parents=True)
            target.write_text("# 条款", encoding="utf-8")
            self.assertEqual(resolve_wikilink(root, "02-条款结构/增值税/条款"), target)

    def test_reverse_graph_tracks_relation_to_provision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            provision = root / "02-条款结构" / "增值税" / "条款.md"
            relation = root / "07-政策效力与关系" / "修改关系" / "关系.md"
            provision.parent.mkdir(parents=True)
            relation.parent.mkdir(parents=True)
            provision.write_text("# 条款", encoding="utf-8")
            relation.write_text("关联 [[02-条款结构/增值税/条款]]", encoding="utf-8")
            graph = build_reverse_link_graph(root)
            self.assertIn("07-政策效力与关系/修改关系/关系.md", graph["02-条款结构/增值税/条款.md"])


class ChunkingTests(unittest.TestCase):
    def test_clause_heading_is_kept(self):
        chunks = chunk_markdown(
            "01-法规原文/国家/增值税/示例.md",
            """---
title: 示例法
---
# 第一章
第一条 纳税人应当依法申报。
第二条 本法自公布之日起施行。
""",
            max_chars=70,
        )
        self.assertTrue(any("第一条" in c["heading"] or "第一条" in c["text"] for c in chunks))


if __name__ == "__main__":
    unittest.main()
