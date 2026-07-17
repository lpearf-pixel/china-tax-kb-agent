from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "90-工具"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from taxkb_core import bm25_rank, chunk_markdown, filter_docs, iter_markdown, select_note_for_profile  # noqa: E402

from .models import EvidenceItem, TaxFacts


class EvidenceRetriever:
    def __init__(self, vault: Path):
        self.vault = Path(vault).resolve()
        self.chunks_path = self.vault / "90-工具/output/chunks.jsonl"
        self._docs: list[dict] | None = None

    def _load_docs(self) -> list[dict]:
        if self._docs is not None:
            return self._docs
        if self.chunks_path.exists():
            self._docs = [
                json.loads(line)
                for line in self.chunks_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return self._docs
        docs: list[dict] = []
        excluded = (
            "90-工具/", "99-归档/", "99-模板/", "10-法规更新记录/",
            "11-问题测试集/", "12-决策记录/", "16-交互工作台/",
            "docs/", ".obsidian/", "apps/",
        )
        for note in iter_markdown(self.vault, excluded):
            rel = note.relative_to(self.vault).as_posix()
            if not select_note_for_profile(rel, "full"):
                continue
            docs.extend(chunk_markdown(rel, note.read_text(encoding="utf-8", errors="replace")))
        self._docs = docs
        return docs

    @staticmethod
    def build_query(facts: TaxFacts) -> str:
        parts = [
            facts.description,
            facts.taxpayer_type,
            facts.vat_status,
            facts.transaction_type,
            facts.amount_period,
            facts.objective,
        ]
        if facts.region == "CN-XJ":
            parts.append("新疆")
        elif facts.region == "CN-HI":
            parts.append("海南")
        if facts.hainan_special_scene or facts.transaction_type == "进口货物":
            parts.extend(["海南自贸港", "一线二线", "零关税", facts.hs_code])
        if facts.related_party:
            parts.extend(["关联交易", "分拆销售额"])
        return " ".join(p for p in parts if p)

    def search(self, facts: TaxFacts, top_k: int = 8) -> list[EvidenceItem]:
        docs = filter_docs(
            self._load_docs(),
            jurisdiction=facts.region,
            valid_on=facts.business_date,
            tax_type=None if facts.transaction_type == "进口货物" else "增值税",
            evidence_tiers={"A"},
            statuses={"effective", "partially_effective"},
        )
        ranked = bm25_rank(self.build_query(facts), docs, top_k=max(top_k * 3, top_k))
        items: list[EvidenceItem] = []
        seen: set[str] = set()
        for doc, score in ranked:
            path = str(doc.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            meta = doc.get("metadata") or {}
            items.append(EvidenceItem(
                path=path,
                title=str(meta.get("title") or doc.get("heading") or Path(path).stem),
                document_number=str(meta.get("document_number") or ""),
                article=str(meta.get("article_number") or meta.get("provision_id") or ""),
                excerpt=str(doc.get("text") or "")[:500],
                score=float(score),
                source_url=str(meta.get("source_url") or ""),
                jurisdiction_scope=str(meta.get("jurisdiction_scope") or "CN"),
                evidence_tier=str(meta.get("evidence_tier") or "A"),
            ))
            if len(items) >= top_k:
                break
        return items
