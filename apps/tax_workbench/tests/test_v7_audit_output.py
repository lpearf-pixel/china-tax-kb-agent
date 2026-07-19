from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.tax_workbench.markdown import render_markdown
from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]


def facts(**overrides):
    payload = {
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
    payload.update(overrides)
    return TaxFacts.from_dict(payload)


class V7AuditOutputTests(unittest.TestCase):
    def test_stateless_analysis_does_not_expose_persisted_case(self):
        with tempfile.TemporaryDirectory() as td:
            result = TaxPlanningService(ROOT, case_root=Path(td)).analyze(facts())
        self.assertEqual(result.case_id, "")
        self.assertEqual(result.case_state, "stateless_analysis")

    def test_markdown_contains_issue_rule_formula_and_score(self):
        with tempfile.TemporaryDirectory() as td:
            result = TaxPlanningService(ROOT, case_root=Path(td)).analyze(facts())
        text = render_markdown(facts(), result)
        for heading in (
            "税务议题树",
            "规则判断轨迹",
            "税额计算与现金流",
            "综合评分",
        ):
            self.assertIn(heading, text)
        self.assertIn("VAT-SMALL-THRESHOLD-QUARTER-2026", text)
        self.assertIn("符合起征点候选", text)


if __name__ == "__main__":
    unittest.main()
