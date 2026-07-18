import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apps.tax_decision_core.domain import CaseRecord, CaseState
from apps.tax_decision_core.storage import CaseStorage


class RetrievalVersionStorageTests(unittest.TestCase):
    def test_evidence_trace_creates_matching_retrieval_version(self):
        with tempfile.TemporaryDirectory() as td:
            storage = CaseStorage(Path(td))
            now = datetime(2026, 7, 18, tzinfo=timezone.utc)
            case = CaseRecord("case-r1", CaseState.DRAFT, "KB", "rules", 1, now, now)
            storage.create(case)
            trace = {"provider": "local_hashing", "selected_count": 3}
            storage.write_version("case-r1", "evidence", 1, {"items": [{"path": "x.md", "retrieval_trace": trace}]})
            self.assertEqual(storage.load_version("case-r1", "retrieval", 1), trace)


if __name__ == "__main__":
    unittest.main()
