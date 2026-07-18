from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apps.tax_decision_core.domain import (
    CaseRecord,
    CaseState,
    Fact,
    FactGraph,
    FactStatus,
    FactVersion,
)
from apps.tax_decision_core.storage import CaseStorage
from apps.tax_decision_core.workflow import CaseWorkflow, WorkflowBlocked


def make_case(storage: CaseStorage, state: CaseState = CaseState.FACTS_PENDING_CONFIRMATION):
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    case = CaseRecord("case-1", state, "kb", "rules-v1", 1, now, now)
    storage.create(case)
    return case


def facts(with_date: bool = True):
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    values = {}
    if with_date:
        values["transaction.business_date"] = Fact(
            "transaction.business_date",
            [
                FactVersion(
                    "transaction.business_date",
                    1,
                    "2026-07-18",
                    FactStatus.CONFIRMED,
                    "test",
                    now,
                    "owner",
                )
            ],
        )
    return FactGraph(facts=values).to_dict()


class WorkflowTests(unittest.TestCase):
    def test_missing_date_blocks_advancement(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            make_case(storage)
            storage.write_version("case-1", "facts", 1, facts(False))
            storage.write_version("case-1", "issues", 1, {"issues": []})
            with self.assertRaises(WorkflowBlocked):
                CaseWorkflow(storage).advance("case-1")

    def test_rule_conflict_goes_to_human_review(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            make_case(storage)
            storage.write_version("case-1", "facts", 1, facts())
            storage.write_version("case-1", "issues", 1, {"issues": []})
            workflow = CaseWorkflow(storage)
            self.assertEqual(workflow.advance("case-1"), CaseState.ISSUES_IDENTIFIED)
            storage.write_version("case-1", "evidence", 1, {"items": []})
            self.assertEqual(workflow.advance("case-1"), CaseState.EVIDENCE_READY)
            storage.write_version(
                "case-1",
                "decisions",
                1,
                {"evaluations": [{"status": "conflict"}]},
            )
            self.assertEqual(
                workflow.advance("case-1"),
                CaseState.HUMAN_REVIEW_PENDING,
            )

    def test_invoice_change_replays_rules_calculation_scenarios(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            make_case(storage, CaseState.SCENARIOS_READY)
            workflow = CaseWorkflow(storage)
            rerun = workflow.replay_affected(
                "case-1",
                ["rules", "calculation", "scenarios"],
            )
            self.assertEqual(rerun, ("rules", "calculation", "scenarios"))
            self.assertEqual(storage.load("case-1").state, CaseState.EVIDENCE_READY)

    def test_checkpoint_reuse_is_hash_based(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            make_case(storage)
            workflow = CaseWorkflow(storage)
            workflow.save_checkpoint("case-1", "rules", {"facts_version": 1}, 2)
            self.assertTrue(
                workflow.checkpoint_reusable(
                    "case-1",
                    "rules",
                    {"facts_version": 1},
                )
            )
            self.assertFalse(
                workflow.checkpoint_reusable(
                    "case-1",
                    "rules",
                    {"facts_version": 2},
                )
            )


if __name__ == "__main__":
    unittest.main()
