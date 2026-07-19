from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .domain import CaseRecord, CaseState, Fact, FactGraph, FactStatus, FactVersion
from .storage import CaseStorage

ALLOWED_NODE_TYPES = {
    "Party",
    "TaxRegistration",
    "Transaction",
    "Contract",
    "InvoiceFlow",
    "CashFlow",
    "GoodsFlow",
    "ServiceFlow",
    "Asset",
    "Relationship",
    "EvidenceDocument",
}
ALLOWED_RELATIONS = {
    "signs",
    "governs",
    "has_invoice_flow",
    "has_cash_flow",
    "has_goods_flow",
    "has_service_flow",
    "controls",
    "relates_to",
    "owns",
    "supports",
}


@dataclass(slots=True, frozen=True)
class MissingFact:
    fact_id: str
    reason: str = "fact_not_found"


@dataclass(slots=True, frozen=True)
class ImpactSet:
    fact_id: str
    old_version: int | None
    new_version: int
    affected_nodes: tuple[str, ...]


class FactGraphService:
    def __init__(
        self,
        storage: CaseStorage,
        *,
        kb_version: str = "KB-2026.07.17-V5-PILOT-XJ-HI",
        rule_set_version: str = "vat-rules-v1",
    ):
        self.storage = storage
        self.kb_version = kb_version
        self.rule_set_version = rule_set_version

    @staticmethod
    def _validate_nodes(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw in nodes:
            node_id = str(raw.get("node_id") or "").strip()
            node_type = str(raw.get("node_type") or "").strip()
            if not node_id:
                raise ValueError("node_id is required")
            if node_type not in ALLOWED_NODE_TYPES:
                raise ValueError(f"unknown node_type: {node_type}")
            if node_id in result:
                raise ValueError(f"duplicate node_id: {node_id}")
            result[node_id] = dict(raw)
        return result

    @staticmethod
    def _validate_edges(
        edges: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for raw in edges:
            source = str(raw.get("source") or "")
            target = str(raw.get("target") or "")
            relation = str(raw.get("relation") or "")
            if source not in nodes or target not in nodes:
                raise ValueError(f"edge references unknown node: {source}->{target}")
            if relation not in ALLOWED_RELATIONS:
                raise ValueError(f"unknown relation: {relation}")
            result.append({"source": source, "relation": relation, "target": target})
        return result

    @staticmethod
    def _build_facts(raw_facts: dict[str, Any], now: datetime) -> dict[str, Fact]:
        facts: dict[str, Fact] = {}
        for fact_id, raw in raw_facts.items():
            if not fact_id or not isinstance(raw, dict) or "value" not in raw:
                raise ValueError(f"invalid fact: {fact_id}")
            version = FactVersion(
                fact_id=fact_id,
                version=1,
                value=raw["value"],
                status=FactStatus(raw.get("status", FactStatus.ASSERTED.value)),
                source=str(raw.get("source", "user")),
                valid_from=raw.get("valid_from"),
                valid_to=raw.get("valid_to"),
                system_time=now,
                actor=str(raw.get("actor", "system")),
                sensitive_level=str(raw.get("sensitive_level", "internal")),
            )
            facts[fact_id] = Fact(fact_id=fact_id, versions=[version])
        return facts

    def create_case(self, payload: dict[str, Any]) -> CaseRecord:
        case_id = str(payload.get("case_id") or "").strip()
        now = datetime.now(timezone.utc)
        nodes = self._validate_nodes(list(payload.get("nodes") or []))
        edges = self._validate_edges(list(payload.get("edges") or []), nodes)
        graph = FactGraph(
            facts=self._build_facts(dict(payload.get("facts") or {}), now),
            nodes=nodes,
            edges=edges,
            version=1,
        )
        case = CaseRecord(
            case_id=case_id,
            state=CaseState.FACTS_PENDING_CONFIRMATION,
            kb_version=self.kb_version,
            rule_set_version=self.rule_set_version,
            facts_version=1,
            created_at=now,
            updated_at=now,
        )
        self.storage.create(case)
        self.storage.write_version(case_id, "facts", 1, graph.to_dict())
        self.storage.append_event(
            case_id,
            {"event": "case_created", "at": now.isoformat(), "facts_version": 1},
        )
        return case

    def load_graph(self, case_id: str, version: int | None = None) -> FactGraph:
        if version is None:
            version = self.storage.latest_version(case_id, "facts")
        return FactGraph.from_dict(self.storage.load_version(case_id, "facts", version))

    @staticmethod
    def get_value(graph: FactGraph, fact_id: str) -> Any | MissingFact:
        fact = graph.facts.get(fact_id)
        current = fact.current if fact else None
        return current.value if current else MissingFact(fact_id)

    @staticmethod
    def _affected_nodes(fact_id: str) -> tuple[str, ...]:
        if fact_id == "transaction.business_date":
            return ("issues", "evidence", "rules", "calculation", "scenarios")
        if fact_id.startswith("invoice."):
            return ("rules", "calculation", "scenarios")
        if fact_id.startswith("cit."):
            return ("issues", "rules", "calculation", "scenarios", "human_review")
        if fact_id.startswith("pit."):
            return (
                "issues",
                "evidence",
                "rules",
                "calculation",
                "scenarios",
                "human_review",
            )
        if fact_id in {"transaction.related_party", "transaction.split_signal"}:
            return ("issues", "rules", "calculation", "scenarios", "human_review")
        if fact_id in {
            "transaction.transaction_type",
            "transaction.cross_border",
        }:
            return (
                "issues",
                "evidence",
                "rules",
                "calculation",
                "scenarios",
                "human_review",
            )
        if fact_id.startswith("transaction."):
            return ("rules", "calculation", "scenarios")
        if fact_id.startswith(("goods_flow.", "hainan.")):
            return (
                "issues",
                "evidence",
                "rules",
                "calculation",
                "scenarios",
                "human_review",
            )
        if fact_id.startswith(("taxpayer.", "region.")):
            return ("issues", "evidence", "rules", "calculation", "scenarios")
        if fact_id.startswith("risk."):
            return ("issues", "rules", "calculation", "scenarios", "human_review")
        return ("issues", "evidence", "rules", "calculation", "scenarios")

    def _new_version(
        self,
        case_id: str,
        fact_id: str,
        value: Any,
        actor: str,
        status: FactStatus,
    ) -> tuple[FactVersion, ImpactSet]:
        case = self.storage.load(case_id)
        graph = self.load_graph(case_id, case.facts_version)
        fact = graph.facts.get(fact_id)
        old_version = None
        source = "user_revision"
        valid_from = None
        valid_to = None
        sensitive_level = "internal"
        if fact is None:
            fact = Fact(fact_id=fact_id)
            graph.facts[fact_id] = fact
        elif fact.current:
            current = fact.current
            old_version = current.version
            current.status = FactStatus.SUPERSEDED
            source = current.source
            valid_from = current.valid_from
            valid_to = current.valid_to
            sensitive_level = current.sensitive_level
        next_fact_version = max((item.version for item in fact.versions), default=0) + 1
        now = datetime.now(timezone.utc)
        created = FactVersion(
            fact_id=fact_id,
            version=next_fact_version,
            value=value,
            status=status,
            source=source,
            valid_from=valid_from,
            valid_to=valid_to,
            system_time=now,
            actor=actor,
            sensitive_level=sensitive_level,
        )
        fact.versions.append(created)
        graph.version = case.facts_version + 1
        self.storage.write_version(case_id, "facts", graph.version, graph.to_dict())
        case.facts_version = graph.version
        case.updated_at = now
        self.storage.update_case(case)
        affected = self._affected_nodes(fact_id)
        self.storage.append_event(
            case_id,
            {
                "event": "fact_revised" if old_version else "fact_added",
                "at": now.isoformat(),
                "fact_id": fact_id,
                "old_version": old_version,
                "new_version": next_fact_version,
                "affected_nodes": list(affected),
            },
        )
        return created, ImpactSet(fact_id, old_version, next_fact_version, affected)

    def confirm_fact(self, case_id: str, fact_id: str, value: Any, actor: str) -> FactVersion:
        created, _ = self._new_version(
            case_id, fact_id, value, actor, FactStatus.CONFIRMED
        )
        return created

    def revise_fact(self, case_id: str, fact_id: str, value: Any, actor: str) -> ImpactSet:
        _, impact = self._new_version(
            case_id, fact_id, value, actor, FactStatus.CONFIRMED
        )
        return impact
