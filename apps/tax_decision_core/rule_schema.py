from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

UNSAFE_KEYS = {"python", "eval", "exec", "import", "expression", "callable"}
ALLOWED_OPERATORS = {"equals", "not_equals", "less_than", "less_or_equal", "greater_than", "greater_or_equal", "in", "not_in", "contains", "exists", "is_true", "is_false"}
ALLOWED_STATUSES = {"effective", "not_yet_effective", "expired", "repealed", "pending_review"}
REQUIRED_FIELDS = {"rule_id", "version", "status", "valid_from", "jurisdiction", "tax_type", "priority", "when", "then", "requires", "legal_basis"}


def _walk_for_unsafe(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_str = str(key)
            if key_str.lower() in UNSAFE_KEYS:
                raise ValueError(f"unsafe DSL key `{key_str}` at {path}")
            _walk_for_unsafe(item, f"{path}.{key_str}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_unsafe(item, f"{path}[{index}]")


def _parse_date(raw: Any, field_name: str, *, optional: bool = False) -> date | None:
    if raw in (None, "") and optional:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _validate_condition(node: Any, path: str = "when") -> None:
    if not isinstance(node, Mapping):
        raise ValueError(f"{path} must be an object")
    keys = set(node)
    groups = keys & {"all", "any", "not"}
    if groups:
        if len(groups) != 1 or len(keys) != 1:
            raise ValueError(f"{path} condition group must contain exactly one of all/any/not")
        group = next(iter(groups))
        child = node[group]
        if group in {"all", "any"}:
            if not isinstance(child, list) or not child:
                raise ValueError(f"{path}.{group} must be a non-empty list")
            for index, item in enumerate(child):
                _validate_condition(item, f"{path}.{group}[{index}]")
        else:
            _validate_condition(child, f"{path}.not")
        return
    allowed = {"fact", "operator", "value"}
    unknown = keys - allowed
    if unknown:
        raise ValueError(f"{path} contains unknown condition keys: {sorted(unknown)}")
    fact = node.get("fact")
    operator = node.get("operator")
    if not isinstance(fact, str) or not fact.strip():
        raise ValueError(f"{path}.fact is required")
    if operator not in ALLOWED_OPERATORS:
        raise ValueError(f"invalid operator at {path}: {operator!r}")
    if operator not in {"exists", "is_true", "is_false"} and "value" not in node:
        raise ValueError(f"{path}.value is required for operator {operator}")


@dataclass(slots=True, frozen=True)
class LegalBasis:
    document_id: str
    provision_id: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LegalBasis":
        document_id = str(data.get("document_id") or "").strip()
        provision_id = str(data.get("provision_id") or "").strip()
        if not document_id:
            raise ValueError("legal_basis.document_id is required")
        return cls(document_id=document_id, provision_id=provision_id)

    def to_mapping(self) -> dict[str, str]:
        payload = {"document_id": self.document_id}
        if self.provision_id:
            payload["provision_id"] = self.provision_id
        return payload


@dataclass(slots=True, frozen=True)
class RuleDefinition:
    rule_id: str
    version: int
    status: str
    valid_from: date
    valid_to: date | None
    jurisdiction: str
    tax_type: str
    priority: int
    when: dict[str, Any]
    then: dict[str, Any]
    requires: tuple[str, ...] = field(default_factory=tuple)
    legal_basis: tuple[LegalBasis, ...] = field(default_factory=tuple)
    exclusive_group: str = ""
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RuleDefinition":
        if not isinstance(data, Mapping):
            raise ValueError("rule must be an object")
        _walk_for_unsafe(data)
        missing = REQUIRED_FIELDS - set(data)
        if missing:
            raise ValueError(f"missing required rule fields: {', '.join(sorted(missing))}")
        rule_id = str(data.get("rule_id") or "").strip()
        if not rule_id:
            raise ValueError("rule_id is required")
        try:
            version = int(data.get("version"))
            priority = int(data.get("priority"))
        except (TypeError, ValueError) as exc:
            raise ValueError("version and priority must be integers") from exc
        if version < 1:
            raise ValueError("version must be >= 1")
        status = str(data.get("status") or "")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"invalid rule status: {status}")
        valid_from = _parse_date(data.get("valid_from"), "valid_from")
        valid_to = _parse_date(data.get("valid_to"), "valid_to", optional=True)
        if valid_to and valid_to < valid_from:
            raise ValueError("valid_to cannot be before valid_from")
        jurisdiction = str(data.get("jurisdiction") or "").strip()
        tax_type = str(data.get("tax_type") or "").strip()
        if not jurisdiction or not tax_type:
            raise ValueError("jurisdiction and tax_type are required")
        when = dict(data.get("when") or {})
        _validate_condition(when)
        then = dict(data.get("then") or {})
        if not str(then.get("outcome") or "").strip():
            raise ValueError("then.outcome is required")
        requires_raw = data.get("requires")
        if not isinstance(requires_raw, list) or any(not isinstance(item, str) or not item.strip() for item in requires_raw):
            raise ValueError("requires must be a list of fact ids")
        legal_raw = data.get("legal_basis")
        if not isinstance(legal_raw, list) or not legal_raw:
            raise ValueError("legal_basis must be a non-empty list")
        legal_basis = tuple(LegalBasis.from_mapping(item) for item in legal_raw)
        tags_raw = data.get("tags", [])
        if not isinstance(tags_raw, list):
            raise ValueError("tags must be a list")
        return cls(rule_id=rule_id, version=version, status=status, valid_from=valid_from, valid_to=valid_to, jurisdiction=jurisdiction, tax_type=tax_type, priority=priority, exclusive_group=str(data.get("exclusive_group") or "").strip(), when=when, then=then, requires=tuple(dict.fromkeys(item.strip() for item in requires_raw)), legal_basis=legal_basis, description=str(data.get("description") or ""), tags=tuple(str(item) for item in tags_raw))

    def is_effective_on(self, valid_on: date) -> bool:
        return self.status == "effective" and self.valid_from <= valid_on and (self.valid_to is None or valid_on <= self.valid_to)

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"rule_id": self.rule_id, "version": self.version, "status": self.status, "valid_from": self.valid_from.isoformat(), "valid_to": self.valid_to.isoformat() if self.valid_to else None, "jurisdiction": self.jurisdiction, "tax_type": self.tax_type, "priority": self.priority, "when": self.when, "then": self.then, "requires": list(self.requires), "legal_basis": [item.to_mapping() for item in self.legal_basis]}
        if self.exclusive_group:
            payload["exclusive_group"] = self.exclusive_group
        if self.description:
            payload["description"] = self.description
        if self.tags:
            payload["tags"] = list(self.tags)
        return payload
