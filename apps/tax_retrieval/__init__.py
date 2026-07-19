"""Version-aware hybrid legal retrieval for TaxKB V7.1."""

from .engine import HybridRetrievalEngine
from .models import (
    EVIDENCE_ROLES,
    QUERY_ROLES,
    EvidenceBundle,
    EvidenceRecord,
    QueryPlan,
    QuerySpec,
    RetrievalCandidate,
    RetrievalTrace,
)
from .query_planner import QueryPlanner
from .vector_index import EmbeddingProvider, HashingVectorIndex, HashingVectorizer

__all__ = [
    "EVIDENCE_ROLES",
    "QUERY_ROLES",
    "EmbeddingProvider",
    "EvidenceBundle",
    "EvidenceRecord",
    "HashingVectorIndex",
    "HashingVectorizer",
    "HybridRetrievalEngine",
    "QueryPlan",
    "QueryPlanner",
    "QuerySpec",
    "RetrievalCandidate",
    "RetrievalTrace",
]
