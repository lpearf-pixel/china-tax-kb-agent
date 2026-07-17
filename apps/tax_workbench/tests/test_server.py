import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from apps.tax_workbench.server import create_server


ROOT = Path(__file__).resolve().parents[3]


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(ROOT, host="127.0.0.1", port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, method="GET", payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def base_payload(self):
        return {
            "business_date": "2026-07-17", "region": "CN-XJ", "taxpayer_type": "企业",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "240000",
            "amount_period": "季度", "invoice_need": "普通发票", "objective": "合规降负", "description": "咨询服务",
        }

    def test_health_and_schema(self):
        status, payload = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        status, payload = self.request("/api/schema")
        self.assertEqual(status, 200)
        self.assertIn("regions", payload)

    def test_invalid_json_returns_400(self):
        req = urllib.request.Request(self.base + "/api/analyze", data=b"{", method="POST", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_missing_required_facts_returns_422(self):
        status, payload = self.request("/api/analyze", "POST", {"region": "CN-XJ"})
        self.assertEqual(status, 422)
        self.assertIn("errors", payload)

    def test_successful_analysis_returns_schemes(self):
        status, payload = self.request("/api/analyze", "POST", self.base_payload())
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["schemes"]), 3)
        self.assertIn("evidence", payload)


if __name__ == "__main__":
    unittest.main()
