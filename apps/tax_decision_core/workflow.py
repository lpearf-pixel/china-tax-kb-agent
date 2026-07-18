from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .domain import CaseState, FactGraph, RuleEvaluationStatus
from .storage import CaseStorage


class WorkflowBlocked(RuntimeError):
    pass


ORDERED_NODES = ("issues", "evidence", "rules", "calculation", "scenarios")
STATE_BEFORE = {
    "issues": CaseState.FACTS_PENDING_CONFIRMATION,
    "evidence": CaseState.ISSUES_IDENTIFIED,
    "rules": CaseState.EVIDENCE_READY,
    "calculation": CaseState.RULES_EVALUATED,
    "scenarios": CaseState.CALCULATION_READY,
}


class CaseWorkflow:
    def __init__(self, storage: CaseStorage):
        self.storage = storage

    def _latest(self, case_id: str, kind: str):
        try:
            version = self.storage.latest_version(case_id, kind)
            return self.storage.load_version(case_id, kind, version)
        except FileNotFoundError:
            return None

    def _facts(self, case_id: str) -> FactGraph:
        payload = self._latest(case_id, "facts")
        return FactGraph.from_dict(payload) if payload else FactGraph()

    @staticmethod
    def _fact_value(graph: FactGraph, fact_id: str):
        fact = graph.facts.get(fact_id)
        current = fact.current if fact else None
        return current.value if current else None

    def advance(self, case_id: str) -> CaseState:
        case = self.storage.load(case_id)
        now = datetime.now(timezone.utc)

        if case.state == CaseState.DRAFT:
            case.state = CaseState.FACTS_PENDING_CONFIRMATION
        elif case.state == CaseState.FACTS_PENDING_CONFIRMATION:
            graph = self._facts(case_id)
            if self._fact_value(graph, "transaction.business_date") in (None, ""):
                raise WorkflowBlocked("business date is required before issue/evidence processing")
            if self._latest(case_id, "issues") is None:
                raise WorkflowBlocked("issues artifact is required")
            case.state = CaseState.ISSUES_IDENTIFIED
        elif case.state == CaseState.ISSUES_IDENTIFIED:
            if self._latest(case_id, "evidence") is None:
                raise WorkflowBlocked("evidence artifact is required")
            case.state = CaseState.EVIDENCE_READY
        elif case.state == CaseState.EVIDENCE_READY:
            decisions = self._latest(case_id, "decisions")
            if decisions is None:
                raise WorkflowBlocked("rule evaluations are required")
            statuses = {str(item.get("status")) for item in decisions.get("evaluations", [])}
            if (
                RuleEvaluationStatus.CONFLICT.value in statuses
                or RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED.value in statuses
            ):
                case.state = CaseState.HUMAN_REVIEW_PENDING
            else:
                case.state = CaseState.RULES_EVALUATED
        elif case.state == CaseState.RULES_EVALUATED:
            if self._latest(case_id, "calculations") is None:
                raise WorkflowBlocked("calculations artifact is required")
            case.state = CaseState.CALCULATION_READY
        elif case.state == CaseState.CALCULATION_READY:
            scenarios = self._latest(case_id, "scenarios")
            if scenarios is None:
                raise WorkflowBlocked("scenarios artifact is required")
            if any(
                bool(item.get("human_review_required"))
                for item in scenarios.get("scenarios", [])
            ):
                case.state = CaseState.HUMAN_REVIEW_PENDING
            else:
                case.state = CaseState.SCENARIOS_READY

        case.updated_at = now
        self.storage.update_case(case)
        self.storage.append_event(
            case_id,
            {"event": "state_advanced", "state": case.state.value, "at": now.isoformat()},
        )
        return case.state

    def record_review(
        self,
        case_id: str,
        approved: bool,
        actor: str,
        note: str = "",
    ) -> CaseState:
        case = self.storage.load(case_id)
        if case.state not in {CaseState.HUMAN_REVIEW_PENDING, CaseState.SCENARIOS_READY}:
            raise WorkflowBlocked("case is not reviewable")
        case.state = CaseState.APPROVED if approved else CaseState.REJECTED
        case.review_status = "approved" if approved else "rejected"
        case.updated_at = datetime.now(timezone.utc)
        self.storage.update_case(case)
        self.storage.append_event(
            case_id,
            {
                "event": "review_recorded",
                "approved": approved,
                "actor": actor,
                "note": note,
                "at": case.updated_at.isoformat(),
            },
        )
        return case.state

    @staticmethod
    def _hash(payload: Any) -> str:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def save_checkpoint(
        self,
        case_id: str,
        node: str,
        input_payload: Any,
        output_version: int,
    ) -> dict[str, Any]:
        if node not in ORDERED_NODES:
            raise ValueError("unknown workflow node")
        payload = {
            "node": node,
            "input_hash": self._hash(input_payload),
            "output_version": output_version,
        }
        try:
            version = self.storage.latest_version(case_id, f"checkpoint-{node}") + 1
        except FileNotFoundError:
            version = 1
        self.storage.write_version(case_id, f"checkpoint-{node}", version, payload)
        return payload

    def checkpoint_reusable(self, case_id: str, node: str, input_payload: Any) -> bool:
        try:
            payload = self._latest(case_id, f"checkpoint-{node}")
        except ValueError:
            return False
        return bool(payload and payload.get("input_hash") == self._hash(input_payload))

    def replay_from(self, case_id: str, node: str) -> tuple[str, ...]:
        if node not in ORDERED_NODES:
            raise ValueError("unknown workflow node")
        index = ORDERED_NODES.index(node)
        rerun = ORDERED_NODES[index:]
        case = self.storage.load(case_id)
        case.state = STATE_BEFORE[node]
        case.updated_at = datetime.now(timezone.utc)
        self.storage.update_case(case)
        self.storage.append_event(
            case_id,
            {
                "event": "workflow_replay",
                "from_node": node,
                "rerun_nodes": list(rerun),
                "at": case.updated_at.isoformat(),
            },
        )
        return rerun

    def replay_affected(
        self,
        case_id: str,
        affected_nodes: list[str] | tuple[str, ...],
    ) -> tuple[str, ...]:
        candidates = [node for node in ORDERED_NODES if node in set(affected_nodes)]
        return self.replay_from(case_id, candidates[0]) if candidates else tuple()
