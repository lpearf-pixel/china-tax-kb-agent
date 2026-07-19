from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

QUERY_ROLES = {"main", "eligibility", "limitation", "exclusion", "version", "local"}
EVIDENCE_ROLES = {"support", "limitation", "exclusion", "historical", "local", "conflict"}


@dataclass(slots=True, frozen=True)
class QuerySpec:
    query_id: str
    role: str
    text: str
    required_terms: tuple[str, ...] = ()
    optional_terms: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("effective", "partially_effective")

    def __post_init__(self) -> None:
        if not self.query_id:
            raise ValueError("query_id is required")
        if self.role not in QUERY_ROLES:
            raise ValueError(f"invalid query role: {self.role}")
        if not self.text.strip():
            raise ValueError("query text is required")
        if len(self.text) > 500:
            raise ValueError("query text exceeds 500 characters")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueryPlan:
    jurisdiction: str
    valid_on: str
    tax_type: str | None
    queries: list[QuerySpec]
    historical_requested: bool = False

    def __post_init__(self) -> None:
        ids = [item.query_id for item in self.queries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate query_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "jurisdiction": self.jurisdiction,
            "valid_on": self.valid_on,
            "tax_type": self.tax_type,
            "historical_requested": self.historical_requested,
            "queries": [item.to_dict() for item in self.queries],
        }


@dataclass(slots=True)
class RetrievalCandidate:
    candidate_id: str
    path: str
    chunk_id: str
    heading: str
    text: str
    metadata: dict[str, Any]
    query_hits: set[str] = field(default_factory=set)
    query_roles: set[str] = field(default_factory=set)
    bm25_ranks: dict[str, int] = field(default_factory=dict)
    vector_ranks: dict[str, int] = field(default_factory=dict)
    bm25_scores: dict[str, float] = field(default_factory=dict)
    vector_scores: dict[str, float] = field(default_factory=dict)
    rrf_score: float = 0.0
    relation_score: float = 0.0
    relation_reasons: list[str] = field(default_factory=list)
    evidence_role: str = "support"
    classification_reasons: list[str] = field(default_factory=list)
    final_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.evidence_role not in EVIDENCE_ROLES:
            raise ValueError(f"invalid evidence role: {self.evidence_role}")

    @property
    def document_id(self) -> str:
        return str(self.metadata.get("document_id") or "")

    @property
    def provision_id(self) -> str:
        return str(self.metadata.get("provision_id") or "")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["query_hits"] = sorted(self.query_hits)
        payload["query_roles"] = sorted(self.query_roles)
        return payload


@dataclass(slots=True)
class EvidenceRecord:
    path: str
    title: str
    document_number: str = ""
    article: str = ""
    excerpt: str = ""
    score: float = 0.0
    source_url: str = ""
    jurisdiction_scope: str = "CN"
    evidence_tier: str = "A"
    role: str = "support"
    document_id: str = ""
    provision_id: str = ""
    valid_from: str = ""
    valid_to: str = ""
    status: str = "effective"
    score_breakdown: dict[str, float] = field(default_factory=dict)
    match_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RetrievalTrace:
    plan: dict[str, Any]
    provider: str = "local_hashing"
    provider_errors: list[str] = field(default_factory=list)
    documents_before_gate: int = 0
    documents_after_gate: int = 0
    candidate_count: int = 0
    relation_expanded_count: int = 0
    selected_count: int = 0
    query_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceBundle:
    support: list[EvidenceRecord] = field(default_factory=list)
    limitation: list[EvidenceRecord] = field(default_factory=list)
    exclusion: list[EvidenceRecord] = field(default_factory=list)
    historical: list[EvidenceRecord] = field(default_factory=list)
    local: list[EvidenceRecord] = field(default_factory=list)
    conflict: list[EvidenceRecord] = field(default_factory=list)
    trace: RetrievalTrace | None = None

    def grouped(self) -> dict[str, list[EvidenceRecord]]:
        return {role: getattr(self, role) for role in sorted(EVIDENCE_ROLES)}

    def flatten_current(self) -> list[EvidenceRecord]:
        seen: set[tuple[str, str]] = set()
        rows: list[EvidenceRecord] = []
        for role in ("support", "local", "limitation", "exclusion"):
            for item in getattr(self, role):
                key = (role, item.provision_id or item.path)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(item)
        return rows

    def to_dict(self) -> dict[str, Any]:
        payload = {role: [item.to_dict() for item in getattr(self, role)] for role in EVIDENCE_ROLES}
        payload["trace"] = self.trace.to_dict() if self.trace else None
        return payload
