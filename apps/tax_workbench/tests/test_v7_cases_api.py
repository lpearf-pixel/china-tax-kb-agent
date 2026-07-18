from __future__ import annotations

import json
import shutil
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from apps.tax_workbench.server import create_server

ROOT = Path(__file__).resolve().parents[3]


class V7CaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(ROOT, host="127.0.0.1", port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.created_cases: list[str] = []

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        for case_id in cls.created_cases:
            shutil.rmtree(ROOT / "cases" / case_id, ignore_errors=True)

    def request(self, path, method="GET", payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    @staticmethod
    def facts():
        return {
            "business_date": "2026-07-17",
            "region": "CN-XJ",
            "taxpayer_type": "企业",
            "vat_status": "小规模纳税人",
            "transaction_type": "服务",
            "amount": "240000",
            "total_sales_same_period": "240000",
            "amount_period": "季度",
            "invoice_need": "普通发票",
            "objective": "合规降负",
            "description": "咨询服务",
        }

    def test_stateless_and_persistent_case_lifecycle(self):
        status, stateless = self.request("/api/analyze", "POST", self.facts())
        self.assertEqual(status, 200)
        self.assertEqual(stateless["case_id"], "")
        self.assertEqual(stateless["case_state"], "stateless_analysis")
        self.assertTrue(stateless["rule_trace"])
        self.assertTrue(stateless["calculations"])

        status, created = self.request("/api/cases", "POST", self.facts())
        self.assertEqual(status, 201)
        case_id = created["case_id"]
        self.created_cases.append(case_id)
        self.assertIn(created["case_state"], {"scenarios_ready", "human_review_pending"})

        status, stored = self.request(f"/api/cases/{case_id}")
        self.assertEqual(status, 200)
        self.assertIsNotNone(stored["decisions"])
        self.assertIsNotNone(stored["calculations"])

        fact_id = urllib.parse.quote("invoice.need_special_invoice", safe="")
        status, revised = self.request(
            f"/api/cases/{case_id}/facts/{fact_id}",
            "PATCH",
            {"value": True, "actor": "owner"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(revised["rerun_nodes"], ["rules", "calculation", "scenarios"])

        status, rerun = self.request(f"/api/cases/{case_id}/analyze", "POST", {})
        self.assertEqual(status, 200)
        self.assertEqual(rerun["case_id"], case_id)

        status, audit = self.request(f"/api/cases/{case_id}/audit")
        self.assertEqual(status, 200)
        events = [item["event"] for item in audit["events"]]
        self.assertIn("fact_revised", events)
        self.assertIn("analysis_persisted", events)


if __name__ == "__main__":
    unittest.main()
