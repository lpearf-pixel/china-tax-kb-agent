from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from apps.tax_decision_core.domain import (
    CaseRecord,
    CaseState,
    Fact,
    FactGraph,
    FactStatus,
    FactVersion,
)
from apps.tax_decision_core.issues import IssueEngine


def graph(values):
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return FactGraph(
        facts={
            key: Fact(
                key,
                [FactVersion(key, 1, value, FactStatus.CONFIRMED, "test", now, "owner")],
            )
            for key, value in values.items()
        }
    )


def case():
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return CaseRecord(
        "case-1",
        CaseState.FACTS_PENDING_CONFIRMATION,
        "kb",
        "rules",
        1,
        now,
        now,
    )


class IssueTests(unittest.TestCase):
    def test_xinjiang_consulting_builds_core_vat_issues(self):
        facts = graph(
            {
                "region.code": "CN-XJ",
                "transaction.business_date": "2026-07-18",
                "transaction.transaction_type": "服务",
                "taxpayer.type": "企业",
                "taxpayer.vat_status": "小规模纳税人",
                "transaction.amount_period": "季度",
                "transaction.total_sales_same_period": Decimal("240000"),
                "invoice.waive_exemption": False,
                "invoice.need_special_invoice": False,
                "taxpayer.rolling_sales": Decimal("240000"),
            }
        )
        issues = IssueEngine().identify(case(), facts)
        ids = {issue.issue_id for issue in issues}
        self.assertTrue(
            {
                "vat-taxable-transaction",
                "vat-threshold",
                "vat-one-percent",
                "vat-invoice-choice",
                "vat-xj-overlay",
            }
            <= ids
        )

    def test_hainan_import_builds_parent_children_and_missing_facts(self):
        facts = graph(
            {
                "region.code": "CN-HI",
                "transaction.business_date": "2026-07-18",
                "transaction.transaction_type": "进口货物",
                "transaction.cross_border": True,
                "taxpayer.type": "企业",
                "taxpayer.vat_status": "一般纳税人",
                "invoice.need_special_invoice": False,
                "invoice.waive_exemption": False,
                "taxpayer.rolling_sales": Decimal("6000000"),
            }
        )
        issues = IssueEngine().identify(case(), facts)
        by_id = {issue.issue_id: issue for issue in issues}
        self.assertIn("vat-hi-special", by_id)
        self.assertEqual(by_id["vat-hi-hs-code"].parent_issue_id, "vat-hi-special")
        self.assertEqual(by_id["vat-hi-hs-code"].missing_fact_ids, ["goods_flow.hs_code"])
        self.assertEqual(by_id["vat-hi-human-review"].risk_level, "high")

    def test_related_split_is_high_risk(self):
        facts = graph(
            {
                "region.code": "CN",
                "transaction.business_date": "2026-07-18",
                "transaction.transaction_type": "服务",
                "taxpayer.type": "企业",
                "taxpayer.vat_status": "小规模纳税人",
                "transaction.related_party": True,
                "transaction.split_signal": True,
                "invoice.need_special_invoice": False,
                "invoice.waive_exemption": False,
                "taxpayer.rolling_sales": Decimal("400000"),
            }
        )
        issues = IssueEngine().identify(case(), facts)
        risk = next(issue for issue in issues if issue.issue_id == "vat-anti-avoidance")
        self.assertEqual(risk.risk_level, "high")


if __name__ == "__main__":
    unittest.main()
