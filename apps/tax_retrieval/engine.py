from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .classifier import EvidenceClassifier
from .fusion import rrf_fuse
from .models import EvidenceBundle, EvidenceRecord, QueryPlan, RetrievalCandidate, RetrievalTrace
from .query_planner import QueryPlanner
from .relation_graph import RelationGraph
from .reranker import DeterministicReranker
from .vector_index import EmbeddingProvider, HashingVectorIndex
from .versioning import VersionResolver


class HybridRetrievalEngine:
    def __init__(self, vault: Path, docs: list[dict] | None = None, embedding_provider: EmbeddingProvider | None = None):
        self.vault = Path(vault).resolve()
        self._docs = docs
        self.embedding_provider = embedding_provider
        self.query_planner = QueryPlanner()
        self.classifier = EvidenceClassifier()
        self.reranker = DeterministicReranker()
        self.version_resolver = VersionResolver()

    def _tools(self):
        tools = self.vault / "90-工具"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from taxkb_core import bm25_rank, chunk_markdown, filter_docs, iter_markdown, select_note_for_profile
        return bm25_rank, chunk_markdown, filter_docs, iter_markdown, select_note_for_profile

    def load_docs(self) -> list[dict]:
        if self._docs is not None:
            return self._docs
        chunks = self.vault / "90-工具/output/chunks.jsonl"
        if chunks.exists():
            self._docs = [json.loads(line) for line in chunks.read_text(encoding="utf-8").splitlines() if line.strip()]
            return self._docs
        _, chunk_markdown, _, iter_markdown, select_note_for_profile = self._tools()
        docs: list[dict] = []
        excluded = ("90-工具/", "99-归档/", "99-模板/", "10-法规更新记录/", "11-问题测试集/", "12-决策记录/", "16-交互工作台/", "docs/", ".obsidian/", "apps/")
        for note in iter_markdown(self.vault, excluded):
            rel = note.relative_to(self.vault).as_posix()
            if select_note_for_profile(rel, "full"):
                docs.extend(chunk_markdown(rel, note.read_text(encoding="utf-8", errors="replace")))
        self._docs = docs
        return docs

    @staticmethod
    def _candidate_id(doc: dict) -> str:
        return str(doc.get("chunk_id") or f"{doc.get('path')}::{doc.get('heading')}")

    def recall(self, plan: QueryPlan, docs: list[dict] | None = None, per_query_k: int = 20) -> tuple[list[RetrievalCandidate], RetrievalTrace]:
        all_docs = docs if docs is not None else self.load_docs()
        bm25_rank, _, filter_docs, _, _ = self._tools()
        trace = RetrievalTrace(plan=plan.to_dict(), documents_before_gate=len(all_docs))
        candidate_map: dict[str, RetrievalCandidate] = {}
        rankings: list[list[str]] = []
        provider_name = "local_hashing"
        for spec in plan.queries:
            gated = filter_docs(all_docs, jurisdiction=plan.jurisdiction, valid_on=plan.valid_on, tax_type=plan.tax_type, evidence_tiers={"A"}, statuses=set(spec.statuses))
            trace.documents_after_gate = max(trace.documents_after_gate, len(gated))
            lexical = bm25_rank(spec.text, gated, top_k=per_query_k)
            vector_rows: list[tuple[dict, float]]
            if self.embedding_provider is not None:
                try:
                    provider_name = self.embedding_provider.__class__.__name__
                    texts = [HashingVectorIndex._doc_text(doc) for doc in gated]
                    vectors = self.embedding_provider.embed([spec.text] + texts)
                    query_vector, doc_vectors = vectors[0], vectors[1:]
                    def cosine(left, right):
                        import math
                        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
                        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0
                    vector_rows = sorted(zip(gated, [cosine(query_vector, row) for row in doc_vectors]), key=lambda item: item[1], reverse=True)[:per_query_k]
                except Exception as exc:
                    trace.provider_errors.append(f"{type(exc).__name__}: {exc}")
                    provider_name = "local_hashing_fallback"
                    vector_rows = HashingVectorIndex(gated).search(spec.text, top_k=per_query_k)
            else:
                vector_rows = HashingVectorIndex(gated).search(spec.text, top_k=per_query_k)
            lexical_ids = [self._candidate_id(doc) for doc, _ in lexical]
            vector_ids = [self._candidate_id(doc) for doc, _ in vector_rows]
            rankings.extend([lexical_ids, vector_ids])
            trace.query_stats[spec.query_id] = {"gated": len(gated), "bm25": len(lexical), "vector": len(vector_rows)}
            for source, rows in (("bm25", lexical), ("vector", vector_rows)):
                for rank, (doc, score) in enumerate(rows, 1):
                    candidate_id = self._candidate_id(doc)
                    candidate = candidate_map.setdefault(candidate_id, RetrievalCandidate(candidate_id=candidate_id, path=str(doc.get("path") or ""), chunk_id=str(doc.get("chunk_id") or candidate_id), heading=str(doc.get("heading") or ""), text=str(doc.get("text") or ""), metadata=dict(doc.get("metadata") or {})))
                    candidate.query_hits.add(spec.query_id)
                    candidate.query_roles.add(spec.role)
                    if source == "bm25":
                        candidate.bm25_ranks[spec.query_id] = rank
                        candidate.bm25_scores[spec.query_id] = float(score)
                    else:
                        candidate.vector_ranks[spec.query_id] = rank
                        candidate.vector_scores[spec.query_id] = float(score)
        fused = rrf_fuse(rankings)
        for candidate_id, candidate in candidate_map.items():
            candidate.rrf_score = fused.get(candidate_id, 0.0)
        trace.provider = provider_name
        trace.candidate_count = len(candidate_map)
        return list(candidate_map.values()), trace

    @staticmethod
    def _record(candidate: RetrievalCandidate) -> EvidenceRecord:
        meta = candidate.metadata
        status = str(meta.get("provision_status") or meta.get("document_status") or meta.get("status") or "effective")
        return EvidenceRecord(path=candidate.path, title=str(meta.get("title") or candidate.heading or Path(candidate.path).stem), document_number=str(meta.get("document_number") or ""), article=str(meta.get("article_number") or meta.get("provision_id") or ""), excerpt=candidate.text[:500], score=candidate.final_score, source_url=str(meta.get("source_url") or ""), jurisdiction_scope=str(meta.get("jurisdiction_scope") or "CN"), evidence_tier=str(meta.get("evidence_tier") or "A"), role=candidate.evidence_role, document_id=candidate.document_id, provision_id=candidate.provision_id, valid_from=str(meta.get("provision_valid_from") or meta.get("effective_date") or ""), valid_to=str(meta.get("provision_valid_to") or meta.get("expiry_date") or ""), status=status, score_breakdown=dict(candidate.score_breakdown), match_reasons=sorted(set(candidate.classification_reasons + candidate.relation_reasons + [f"query:{query_id}" for query_id in candidate.query_hits])))

    def search_bundle(self, facts: Any, issues: list[Any] | None = None, top_k: int = 8) -> EvidenceBundle:
        plan = self.query_planner.plan(facts, issues)
        all_docs = self.load_docs()
        candidates, trace = self.recall(plan, all_docs, per_query_k=max(top_k * 3, 12))
        by_path: dict[str, list[dict]] = {}
        for doc in all_docs:
            by_path.setdefault(str(doc.get("path") or ""), []).append(doc)
        _, _, filter_docs, _, _ = self._tools()
        allowed_statuses = {"effective", "partially_effective"}
        if plan.historical_requested:
            allowed_statuses.update({"repealed", "expired"})
        relation_allowed = filter_docs(all_docs, jurisdiction=plan.jurisdiction, valid_on=plan.valid_on, tax_type=plan.tax_type, evidence_tiers={"A"}, statuses=allowed_statuses)
        allowed_paths = {str(doc.get("path") or "") for doc in relation_allowed}
        relation_graph = RelationGraph.build(self.vault, all_docs)
        top_seed = sorted(candidates, key=lambda row: row.rrf_score, reverse=True)[: max(top_k * 2, 10)]
        known = {row.candidate_id for row in candidates}
        expanded = 0
        expansion_limit = max(top_k * 3, 12)
        for seed in top_seed:
            if expanded >= expansion_limit:
                break
            for neighbor_path, reasons in relation_graph.neighbors(seed.path):
                if expanded >= expansion_limit:
                    break
                if neighbor_path not in allowed_paths:
                    continue
                rows = by_path.get(neighbor_path, [])
                if not rows:
                    continue
                doc = rows[0]
                candidate_id = self._candidate_id(doc)
                if candidate_id in known:
                    target = next(row for row in candidates if row.candidate_id == candidate_id)
                else:
                    target = RetrievalCandidate(candidate_id=candidate_id, path=neighbor_path, chunk_id=str(doc.get("chunk_id") or candidate_id), heading=str(doc.get("heading") or ""), text=str(doc.get("text") or ""), metadata=dict(doc.get("metadata") or {}), rrf_score=seed.rrf_score * 0.35)
                    candidates.append(target)
                    known.add(candidate_id)
                    expanded += 1
                target.relation_score = max(target.relation_score, 3.0)
                target.relation_reasons.extend(reasons)
        trace.relation_expanded_count = expanded
        for candidate in candidates:
            role, reasons = self.classifier.classify(candidate, plan.jurisdiction)
            candidate.evidence_role = role
            candidate.classification_reasons = reasons
        candidates = self.version_resolver.resolve(candidates, plan.valid_on, plan.historical_requested)
        ranked = self.reranker.rank(candidates, plan, top_k=max(top_k * 6, 30))
        bundle = EvidenceBundle(trace=trace)
        role_limits = {"support": top_k, "limitation": top_k, "exclusion": top_k, "local": top_k, "historical": top_k, "conflict": top_k}
        seen: dict[str, set[str]] = {role: set() for role in role_limits}
        for candidate in ranked:
            role = candidate.evidence_role
            key = candidate.provision_id or candidate.path
            if key in seen[role] or len(getattr(bundle, role)) >= role_limits[role]:
                continue
            seen[role].add(key)
            getattr(bundle, role).append(self._record(candidate))
        trace.selected_count = sum(len(rows) for rows in bundle.grouped().values())
        return bundle
