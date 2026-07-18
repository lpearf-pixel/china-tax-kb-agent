from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .domain import CaseState
from .storage import CaseStorage


@dataclass(slots=True)
class LawImpactIndex:
    provision_to_rules: dict[str, set[str]] = field(default_factory=dict)
    rule_to_cases: dict[str, set[str]] = field(default_factory=dict)
    case_to_scenarios: dict[str, set[str]] = field(default_factory=dict)

    def register_rule(self, rule_id: str, provision_ids: list[str]) -> None:
        for provision_id in provision_ids:
            self.provision_to_rules.setdefault(provision_id, set()).add(rule_id)

    def register_case(
        self,
        case_id: str,
        rule_ids: list[str],
        scenario_ids: list[str],
    ) -> None:
        for rule_id in rule_ids:
            self.rule_to_cases.setdefault(rule_id, set()).add(case_id)
        self.case_to_scenarios.setdefault(case_id, set()).update(scenario_ids)

    def analyze_change(self, provision_ids: list[str]) -> dict:
        rules: set[str] = set()
        cases: set[str] = set()
        scenarios: set[str] = set()
        for provision_id in provision_ids:
            rules.update(self.provision_to_rules.get(provision_id, set()))
        for rule_id in rules:
            cases.update(self.rule_to_cases.get(rule_id, set()))
        for case_id in cases:
            scenarios.update(self.case_to_scenarios.get(case_id, set()))
        return {
            "provision_ids": sorted(set(provision_ids)),
            "rule_ids": sorted(rules),
            "case_ids": sorted(cases),
            "scenario_ids": sorted(scenarios),
        }

    def to_dict(self) -> dict:
        return {
            "provision_to_rules": {
                key: sorted(values) for key, values in self.provision_to_rules.items()
            },
            "rule_to_cases": {
                key: sorted(values) for key, values in self.rule_to_cases.items()
            },
            "case_to_scenarios": {
                key: sorted(values) for key, values in self.case_to_scenarios.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LawImpactIndex":
        return cls(
            provision_to_rules={
                key: set(values) for key, values in data.get("provision_to_rules", {}).items()
            },
            rule_to_cases={
                key: set(values) for key, values in data.get("rule_to_cases", {}).items()
            },
            case_to_scenarios={
                key: set(values) for key, values in data.get("case_to_scenarios", {}).items()
            },
        )


def mark_affected_cases(
    storage: CaseStorage,
    report: dict,
    *,
    change_id: str,
    new_rule_set_version: str | None = None,
) -> list[str]:
    marked: list[str] = []
    for case_id in report.get("case_ids", []):
        try:
            case = storage.load(case_id)
        except FileNotFoundError:
            continue
        if case.state == CaseState.ARCHIVED:
            continue
        old_state = case.state
        old_rule_set = case.rule_set_version
        case.state = CaseState.AFFECTED_BY_LAW_CHANGE
        case.review_status = "re_review_required"
        case.updated_at = datetime.now(timezone.utc)
        storage.update_case(case)
        storage.append_event(
            case_id,
            {
                "event": "affected_by_law_change",
                "change_id": change_id,
                "at": case.updated_at.isoformat(),
                "old_state": old_state.value,
                "old_rule_set_version": old_rule_set,
                "suggested_rule_set_version": new_rule_set_version,
                "rule_ids": report.get("rule_ids", []),
                "scenario_ids": report.get("scenario_ids", []),
            },
        )
        marked.append(case_id)
    return marked


def write_machine_report(path: Path, report: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
