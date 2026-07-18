from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class FactStatus(str, Enum):
    ASSERTED = "asserted"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"


class CaseState(str, Enum):
    DRAFT = "draft"
    FACTS_PENDING_CONFIRMATION = "facts_pending_confirmation"
    ISSUES_IDENTIFIED = "issues_identified"
    EVIDENCE_READY = "evidence_ready"
    RULES_EVALUATED = "rules_evaluated"
    CALCULATION_READY = "calculation_ready"
    SCENARIOS_READY = "scenarios_ready"
    HUMAN_REVIEW_PENDING = "human_review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AFFECTED_BY_LAW_CHANGE = "affected_by_law_change"
    ARCHIVED = "archived"


class RuleEvaluationStatus(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_FACTS = "insufficient_facts"
    CONFLICT = "conflict"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        kind = value.get("__type__")
        if kind == "decimal":
            return Decimal(str(value["value"]))
        if kind == "datetime":
            return datetime.fromisoformat(str(value["value"]))
        if kind == "date":
            return date.fromisoformat(str(value["value"]))
        return {key: _decode(item) for key, item in value.items()}
    return value


def _enum(enum_type: type[Enum], raw: Any):
    try:
        return enum_type(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {enum_type.__name__}: {raw!r}") from exc


@dataclass(slots=True)
class FactVersion:
    fact_id: str
    version: int
    value: Any
    status: FactStatus
    source: str
    system_time: datetime
    actor: str
    valid_from: date | None = None
    valid_to: date | None = None
    sensitive_level: str = "internal"

    def __post_init__(self) -> None:
        if not self.fact_id:
            raise ValueError("fact_id is required")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if not isinstance(self.status, FactStatus):
            self.status = _enum(FactStatus, self.status)
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot be before valid_from")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "version": self.version,
            "value": _encode(self.value),
            "status": self.status.value,
            "source": self.source,
            "valid_from": _encode(self.valid_from),
            "valid_to": _encode(self.valid_to),
            "system_time": _encode(self.system_time),
            "actor": self.actor,
            "sensitive_level": self.sensitive_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactVersion":
        return cls(
            fact_id=str(data["fact_id"]),
            version=int(data["version"]),
            value=_decode(data.get("value")),
            status=_enum(FactStatus, data.get("status")),
            source=str(data.get("source", "")),
            valid_from=_decode(data.get("valid_from")),
            valid_to=_decode(data.get("valid_to")),
            system_time=_decode(data.get("system_time")),
            actor=str(data.get("actor", "")),
            sensitive_level=str(data.get("sensitive_level", "internal")),
        )


@dataclass(slots=True)
class Fact:
    fact_id: str
    versions: list[FactVersion] = field(default_factory=list)

    @property
    def current(self) -> FactVersion | None:
        active = [item for item in self.versions if item.status != FactStatus.SUPERSEDED]
        return max(active, key=lambda item: item.version) if active else None

    def to_dict(self) -> dict[str, Any]:
        return {"fact_id": self.fact_id, "versions": [item.to_dict() for item in self.versions]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fact":
        return cls(str(data["fact_id"]), [FactVersion.from_dict(item) for item in data.get("versions", [])])


@dataclass(slots=True)
class FactGraph:
    facts: dict[str, Fact] = field(default_factory=dict)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": {key: value.to_dict() for key, value in self.facts.items()},
            "nodes": _encode(self.nodes),
            "edges": _encode(self.edges),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactGraph":
        return cls(
            facts={key: Fact.from_dict(value) for key, value in data.get("facts", {}).items()},
            nodes=_decode(data.get("nodes", {})),
            edges=_decode(data.get("edges", [])),
            version=int(data.get("version", 1)),
        )


@dataclass(slots=True)
class TaxIssue:
    issue_id: str
    tax_type: str
    issue_type: str
    related_fact_ids: list[str] = field(default_factory=list)
    required_fact_ids: list[str] = field(default_factory=list)
    missing_fact_ids: list[str] = field(default_factory=list)
    parent_issue_id: str | None = None
    risk_level: str = "low"
    status: str = "identified"

    def to_dict(self) -> dict[str, Any]:
        return _encode({name: getattr(self, name) for name in self.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaxIssue":
        return cls(**_decode(data))


@dataclass(slots=True)
class RuleEvaluation:
    rule_id: str
    status: RuleEvaluationStatus
    outcome: str = ""
    value: Any = None
    missing_fact_ids: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    legal_basis: list[dict[str, str]] = field(default_factory=list)
    priority: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.status, RuleEvaluationStatus):
            self.status = _enum(RuleEvaluationStatus, self.status)

    def to_dict(self) -> dict[str, Any]:
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__}
        return _encode(payload)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleEvaluation":
        payload = _decode(data)
        payload["status"] = _enum(RuleEvaluationStatus, payload["status"])
        return cls(**payload)


@dataclass(slots=True)
class CalculationResult:
    calculation_id: str
    status: str
    tax_type: str
    taxable_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    deductible_input_tax: Decimal | None = None
    payable_or_credit: Decimal | None = None
    formula: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    rule_ids: list[str] = field(default_factory=list)
    cashflow_events: list[dict[str, Any]] = field(default_factory=list)
    missing_fact_ids: list[str] = field(default_factory=list)
    rounding: str = "ROUND_HALF_UP:0.01"

    def to_dict(self) -> dict[str, Any]:
        return _encode({name: getattr(self, name) for name in self.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalculationResult":
        return cls(**_decode(data))


@dataclass(slots=True)
class Scenario:
    scenario_id: str
    name: str
    decision_variables: dict[str, Any] = field(default_factory=dict)
    calculation_ids: list[str] = field(default_factory=list)
    total_tax: Decimal | None = None
    cashflow_summary: dict[str, Any] = field(default_factory=dict)
    score_components: dict[str, Decimal] = field(default_factory=dict)
    total_score: Decimal | None = None
    risks: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    human_review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _encode({name: getattr(self, name) for name in self.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return cls(**_decode(data))


@dataclass(slots=True)
class CaseRecord:
    case_id: str
    state: CaseState
    kb_version: str
    rule_set_version: str
    facts_version: int
    created_at: datetime
    updated_at: datetime
    issues_version: int = 0
    calculations_version: int = 0
    scenarios_version: int = 0
    review_status: str = "not_requested"

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id is required")
        if not isinstance(self.state, CaseState):
            self.state = _enum(CaseState, self.state)
        for field_name in ("facts_version", "issues_version", "calculations_version", "scenarios_version"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return _encode({name: getattr(self, name) for name in self.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseRecord":
        payload = _decode(data)
        payload["state"] = _enum(CaseState, payload["state"])
        return cls(**payload)
