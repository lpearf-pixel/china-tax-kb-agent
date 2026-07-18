from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .domain import FactGraph, RuleEvaluation, RuleEvaluationStatus
from .rule_schema import RuleDefinition

MISSING = object()


@dataclass(slots=True)
class EvaluationBundle:
    evaluations: list[RuleEvaluation] = field(default_factory=list)
    selected: dict[str, RuleEvaluation] = field(default_factory=dict)
    conflicts: list[RuleEvaluation] = field(default_factory=list)


def _value_from_facts(facts: FactGraph | Mapping[str, Any], fact_id: str) -> Any:
    if isinstance(facts, FactGraph):
        fact = facts.facts.get(fact_id)
        current = fact.current if fact else None
        return current.value if current is not None and current.value is not None else MISSING
    if fact_id in facts:
        value = facts[fact_id]
        return MISSING if value is None else value
    value: Any = facts
    for part in fact_id.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return MISSING
        value = value[part]
    return MISSING if value is None else value


def _coerce_pair(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, Decimal) or (isinstance(right, (int, float, Decimal)) and isinstance(left, (int, float, Decimal))):
        try:
            return Decimal(str(left)), Decimal(str(right))
        except (InvalidOperation, ValueError):
            pass
    if isinstance(left, date) and not isinstance(left, datetime) and isinstance(right, str):
        try:
            return left, date.fromisoformat(right)
        except ValueError:
            pass
    if isinstance(left, datetime) and isinstance(right, str):
        try:
            return left, datetime.fromisoformat(right)
        except ValueError:
            pass
    return left, right


def _compare(actual: Any, operator: str, expected: Any = None) -> bool:
    if operator == "exists":
        return actual is not MISSING
    if actual is MISSING:
        return False
    if operator == "is_true":
        return actual is True
    if operator == "is_false":
        return actual is False
    left, right = _coerce_pair(actual, expected)
    if operator == "equals": return left == right
    if operator == "not_equals": return left != right
    if operator == "less_than": return left < right
    if operator == "less_or_equal": return left <= right
    if operator == "greater_than": return left > right
    if operator == "greater_or_equal": return left >= right
    if operator == "in": return left in right
    if operator == "not_in": return left not in right
    if operator == "contains": return right in left
    raise ValueError(f"unsupported operator: {operator}")


class RuleEngine:
    def _condition(self, node: Mapping[str, Any], facts: FactGraph | Mapping[str, Any]) -> tuple[bool | None, list[str], list[dict[str, Any]]]:
        if "all" in node:
            missing: list[str] = []
            trace: list[dict[str, Any]] = []
            saw_unknown = False
            for child in node["all"]:
                result, child_missing, child_trace = self._condition(child, facts)
                missing.extend(child_missing); trace.extend(child_trace)
                if result is False: return False, sorted(set(missing)), trace
                if result is None: saw_unknown = True
            return (None if saw_unknown else True), sorted(set(missing)), trace
        if "any" in node:
            missing: list[str] = []
            trace: list[dict[str, Any]] = []
            saw_unknown = False
            for child in node["any"]:
                result, child_missing, child_trace = self._condition(child, facts)
                missing.extend(child_missing); trace.extend(child_trace)
                if result is True: return True, sorted(set(missing)), trace
                if result is None: saw_unknown = True
            return (None if saw_unknown else False), sorted(set(missing)), trace
        if "not" in node:
            result, missing, trace = self._condition(node["not"], facts)
            return (None if result is None else not result), missing, trace
        fact_id = str(node["fact"])
        operator = str(node["operator"])
        expected = node.get("value")
        actual = _value_from_facts(facts, fact_id)
        if actual is MISSING and operator != "exists":
            return None, [fact_id], [{"fact": fact_id, "operator": operator, "expected": expected, "missing": True}]
        result = _compare(actual, operator, expected)
        return result, [], [{"fact": fact_id, "operator": operator, "expected": expected, "actual": None if actual is MISSING else actual, "result": result}]

    def evaluate(self, rule: RuleDefinition, facts: FactGraph | Mapping[str, Any], valid_on: date) -> RuleEvaluation:
        if not rule.is_effective_on(valid_on):
            return RuleEvaluation(rule_id=rule.rule_id, status=RuleEvaluationStatus.NOT_APPLICABLE, trace=[{"reason": "rule_not_effective_on_date", "valid_on": valid_on.isoformat()}], legal_basis=[item.to_mapping() for item in rule.legal_basis], priority=rule.priority)
        missing_required = sorted({fact_id for fact_id in rule.requires if _value_from_facts(facts, fact_id) is MISSING})
        if missing_required:
            return RuleEvaluation(rule_id=rule.rule_id, status=RuleEvaluationStatus.INSUFFICIENT_FACTS, missing_fact_ids=missing_required, trace=[{"reason": "required_facts_missing", "facts": missing_required}], legal_basis=[item.to_mapping() for item in rule.legal_basis], priority=rule.priority)
        matched, missing, trace = self._condition(rule.when, facts)
        if matched is None:
            return RuleEvaluation(rule_id=rule.rule_id, status=RuleEvaluationStatus.INSUFFICIENT_FACTS, missing_fact_ids=missing, trace=trace, legal_basis=[item.to_mapping() for item in rule.legal_basis], priority=rule.priority)
        if not matched:
            return RuleEvaluation(rule_id=rule.rule_id, status=RuleEvaluationStatus.NOT_APPLICABLE, trace=trace, legal_basis=[item.to_mapping() for item in rule.legal_basis], priority=rule.priority)
        manual = bool(rule.then.get("manual_review_required")) or rule.then.get("confidence") == "manual_review"
        return RuleEvaluation(rule_id=rule.rule_id, status=RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED if manual else RuleEvaluationStatus.APPLICABLE, outcome=str(rule.then.get("outcome") or ""), value=rule.then.get("value"), trace=trace, legal_basis=[item.to_mapping() for item in rule.legal_basis], priority=rule.priority)

    def evaluate_all(self, rules: list[RuleDefinition], facts: FactGraph | Mapping[str, Any], valid_on: date) -> EvaluationBundle:
        evaluations = [self.evaluate(rule, facts, valid_on) for rule in rules]
        applicable_statuses = {RuleEvaluationStatus.APPLICABLE, RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED}
        by_group: dict[str, list[tuple[RuleDefinition, RuleEvaluation]]] = {}
        for rule, evaluation in zip(rules, evaluations):
            if rule.exclusive_group and evaluation.status in applicable_statuses:
                by_group.setdefault(rule.exclusive_group, []).append((rule, evaluation))
        selected: dict[str, RuleEvaluation] = {}
        conflicts: list[RuleEvaluation] = []
        for group, candidates in by_group.items():
            top_priority = max(item[0].priority for item in candidates)
            top = [(rule, evaluation) for rule, evaluation in candidates if rule.priority == top_priority]
            signatures = {(evaluation.outcome, repr(evaluation.value)) for _, evaluation in top}
            if len(signatures) > 1:
                conflicts.append(RuleEvaluation(rule_id=f"conflict:{group}", status=RuleEvaluationStatus.CONFLICT, outcome=group, trace=[{"reason": "exclusive_group_conflict", "group": group, "priority": top_priority, "rules": [rule.rule_id for rule, _ in top]}], priority=top_priority))
            else:
                top.sort(key=lambda item: item[0].rule_id)
                selected[group] = top[0][1]
        return EvaluationBundle(evaluations=evaluations, selected=selected, conflicts=conflicts)
