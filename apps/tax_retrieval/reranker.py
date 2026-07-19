from __future__ import annotations

import re

from .models import QueryPlan, RetrievalCandidate


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_%.-]+|[\u4e00-\u9fff]{2,}", text.lower()))


class DeterministicReranker:
    ROLE_MATCH = {
        "support": {"main", "eligibility"},
        "limitation": {"limitation"},
        "exclusion": {"exclusion"},
        "historical": {"version"},
        "local": {"local"},
        "conflict": {"version", "limitation"},
    }

    def rank(self, candidates: list[RetrievalCandidate], plan: QueryPlan, top_k: int = 20) -> list[RetrievalCandidate]:
        query_terms = _terms(" ".join(item.text for item in plan.queries))
        for candidate in candidates:
            meta = candidate.metadata
            title_text = " ".join(str(value) for value in (meta.get("title"), meta.get("article_number"), candidate.heading) if value)
            exact_hits = len(query_terms & _terms(title_text))
            scope = str(meta.get("jurisdiction_scope") or "CN")
            tier = str(meta.get("evidence_tier") or "").upper()
            role_match = len(self.ROLE_MATCH.get(candidate.evidence_role, set()) & candidate.query_roles)
            path_bonus = 8.0 if candidate.path.startswith("02-条款结构/") else 5.0 if candidate.path.startswith("01-法规原文/") else 2.0 if candidate.path.startswith("07-政策效力与关系/") else 0.0
            length_penalty = min(4.0, max(0.0, (len(candidate.text) - 900) / 350.0))
            breakdown = {
                "rrf": min(40.0, candidate.rrf_score * 1200.0),
                "exact_title": min(15.0, exact_hits * 3.0),
                "role_coverage": min(10.0, role_match * 5.0),
                "jurisdiction": 8.0 if scope == plan.jurisdiction else 5.0 if scope == "CN" else 0.0,
                "evidence_tier": 8.0 if tier == "A" else -8.0,
                "knowledge_layer": path_bonus,
                "relation": min(5.0, candidate.relation_score),
                "length_penalty": -length_penalty,
            }
            candidate.score_breakdown = breakdown
            candidate.final_score = sum(breakdown.values())
        candidates.sort(key=lambda row: (row.final_score, row.rrf_score, row.path), reverse=True)
        return candidates[:top_k]
