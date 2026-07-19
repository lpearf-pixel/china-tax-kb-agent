from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.tax_retrieval import EvidenceBundle, EvidenceRecord, HybridRetrievalEngine
from .models import EvidenceItem, TaxFacts


class EvidenceRetriever:
    def __init__(self, vault: Path, *, engine: HybridRetrievalEngine | None = None):
        self.vault = Path(vault).resolve()
        self.engine = engine or HybridRetrievalEngine(self.vault)
        self.last_bundle: EvidenceBundle | None = None

    @staticmethod
    def _item(record: EvidenceRecord, trace: dict[str, Any] | None = None) -> EvidenceItem:
        return EvidenceItem(path=record.path, title=record.title, document_number=record.document_number, article=record.article, excerpt=record.excerpt, score=record.score, source_url=record.source_url, jurisdiction_scope=record.jurisdiction_scope, evidence_tier=record.evidence_tier, role=record.role, document_id=record.document_id, provision_id=record.provision_id, valid_from=record.valid_from, valid_to=record.valid_to, status=record.status, score_breakdown=dict(record.score_breakdown), match_reasons=list(record.match_reasons), _retrieval_trace=dict(trace or {}))

    def search_bundle(self, facts: TaxFacts, issues: list[Any] | None = None, top_k: int = 8) -> EvidenceBundle:
        self.last_bundle = self.engine.search_bundle(facts, issues, top_k)
        return self.last_bundle

    def search(self, facts: TaxFacts, top_k: int = 8) -> list[EvidenceItem]:
        bundle = self.search_bundle(facts, top_k=top_k)
        if not bundle.support:
            return []
        trace = bundle.trace.to_dict() if bundle.trace else {}
        return [self._item(record, trace if index == 0 else None) for index, record in enumerate(bundle.flatten_current())]
