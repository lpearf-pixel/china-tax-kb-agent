from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apps.tax_decision_core.domain import CaseRecord, CaseState
from apps.tax_decision_core.storage import CaseStorage


class CaseStorageTests(unittest.TestCase):
    def make_case(self) -> CaseRecord:
        now = datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc)
        return CaseRecord(
            case_id="case-001",
            state=CaseState.DRAFT,
            kb_version="KB-2026.07.17-V5-PILOT-XJ-HI",
            rule_set_version="vat-rules-v1",
            facts_version=1,
            created_at=now,
            updated_at=now,
        )

    def test_create_load_version_and_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            case = self.make_case()

            path = storage.create(case)
            self.assertEqual(path, Path(td) / "case-001" / "case.json")
            self.assertEqual(storage.load("case-001"), case)

            version_path = storage.write_version("case-001", "facts", 1, {"facts": [1, 2]})
            self.assertEqual(version_path.name, "facts-v001.json")
            self.assertEqual(json.loads(version_path.read_text(encoding="utf-8")), {"facts": [1, 2]})

            storage.append_event("case-001", {"event": "case_created", "at": "2026-07-18T01:00:00Z"})
            timeline = (Path(td) / "case-001" / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(timeline[0])["event"], "case_created")

    def test_does_not_overwrite_case_or_version(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            case = self.make_case()
            storage.create(case)
            with self.assertRaises(FileExistsError):
                storage.create(case)

            storage.write_version("case-001", "facts", 1, {"x": 1})
            with self.assertRaises(FileExistsError):
                storage.write_version("case-001", "facts", 1, {"x": 2})

    def test_rejects_path_traversal_and_invalid_kind(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            for bad_id in ("", "../escape", "a/b", "a\\b", ".hidden"):
                with self.subTest(bad_id=bad_id):
                    with self.assertRaises(ValueError):
                        storage.load(bad_id)
            storage.create(self.make_case())
            with self.assertRaises(ValueError):
                storage.write_version("case-001", "../facts", 1, {})


if __name__ == "__main__":
    unittest.main()
