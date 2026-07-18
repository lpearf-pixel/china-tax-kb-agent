from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apps.tax_decision_core.domain import CaseRecord, CaseState
from apps.tax_decision_core.impact import LawImpactIndex, mark_affected_cases, write_machine_report
from apps.tax_decision_core.storage import CaseStorage


class ImpactTests(unittest.TestCase):
    def test_provision_to_rule_case_scenario_chain(self):
        index = LawImpactIndex()
        index.register_rule("R1", ["P1"])
        index.register_case("C1", ["R1"], ["S1"])
        report = index.analyze_change(["P1"])
        self.assertEqual(report["rule_ids"], ["R1"])
        self.assertEqual(report["case_ids"], ["C1"])
        self.assertEqual(report["scenario_ids"], ["S1"])

    def test_approved_case_is_marked_but_rule_version_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            now = datetime(2026, 7, 18, tzinfo=timezone.utc)
            case = CaseRecord(
                "C1",
                CaseState.APPROVED,
                "kb",
                "rules-v1",
                1,
                now,
                now,
                review_status="approved",
            )
            storage.create(case)
            marked = mark_affected_cases(
                storage,
                {"case_ids": ["C1"], "rule_ids": ["R1"], "scenario_ids": ["S1"]},
                change_id="chg-1",
                new_rule_set_version="rules-v2",
            )
            loaded = storage.load("C1")
            self.assertEqual(marked, ["C1"])
            self.assertEqual(loaded.state, CaseState.AFFECTED_BY_LAW_CHANGE)
            self.assertEqual(loaded.rule_set_version, "rules-v1")
            self.assertEqual(loaded.review_status, "re_review_required")
            path = write_machine_report(Path(td) / "impact.json", {"x": 1})
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
