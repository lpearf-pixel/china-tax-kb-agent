from __future__ import annotations

from typing import Any

from .domain import CaseRecord, FactGraph, TaxIssue

MISSING = object()


def _fact(graph: FactGraph, fact_id: str) -> Any:
    item = graph.facts.get(fact_id)
    current = item.current if item else None
    return current.value if current is not None and current.value is not None else MISSING


def _issue(
    issue_id: str,
    issue_type: str,
    required: list[str],
    graph: FactGraph,
    *,
    parent: str | None = None,
    risk: str = "low",
    related: list[str] | None = None,
) -> TaxIssue:
    missing = [fact_id for fact_id in required if _fact(graph, fact_id) is MISSING]
    return TaxIssue(
        issue_id=issue_id,
        tax_type="增值税",
        issue_type=issue_type,
        related_fact_ids=list(related or required),
        required_fact_ids=list(required),
        missing_fact_ids=missing,
        parent_issue_id=parent,
        risk_level=risk,
        status="facts_missing" if missing else "identified",
    )


class IssueEngine:
    """Build a deterministic VAT issue tree from the confirmed fact graph."""

    def identify(self, case: CaseRecord, facts: FactGraph) -> list[TaxIssue]:
        issues: list[TaxIssue] = []
        issues.append(
            _issue(
                "vat-taxable-transaction",
                "是否属于增值税应税交易",
                ["transaction.transaction_type", "transaction.business_date", "region.code"],
                facts,
            )
        )
        issues.append(
            _issue(
                "vat-taxpayer-status",
                "纳税义务主体与增值税身份",
                ["taxpayer.vat_status", "taxpayer.type"],
                facts,
            )
        )
        issues.append(
            _issue(
                "vat-threshold",
                "小规模纳税人起征点适用",
                [
                    "taxpayer.vat_status",
                    "transaction.amount_period",
                    "transaction.total_sales_same_period",
                    "invoice.waive_exemption",
                ],
                facts,
            )
        )
        issues.append(
            _issue(
                "vat-one-percent",
                "小规模3%减按1%适用",
                ["taxpayer.vat_status", "transaction.transaction_type", "transaction.business_date"],
                facts,
            )
        )
        issues.append(
            _issue(
                "vat-invoice-choice",
                "发票类型与放弃优惠",
                ["invoice.need_special_invoice", "invoice.waive_exemption"],
                facts,
            )
        )
        issues.append(
            _issue(
                "vat-general-registration",
                "一般纳税人登记义务",
                ["taxpayer.rolling_sales", "taxpayer.vat_status"],
                facts,
                risk="medium",
            )
        )

        related = _fact(facts, "transaction.related_party") is True
        split = _fact(facts, "transaction.split_signal") is True
        if related or split:
            issues.append(
                _issue(
                    "vat-anti-avoidance",
                    "关联交易、主体分拆与合理商业目的",
                    ["transaction.related_party", "transaction.split_signal"],
                    facts,
                    risk="high",
                )
            )

        region = _fact(facts, "region.code")
        tx_type = _fact(facts, "transaction.transaction_type")
        cross_border = _fact(facts, "transaction.cross_border") is True
        special = _fact(facts, "hainan.special_scene") is True
        if region == "CN-HI":
            if special or cross_border or tx_type == "进口货物":
                parent = "vat-hi-special"
                issues.append(
                    _issue(
                        parent,
                        "海南自贸港特殊政策路由",
                        ["region.code", "transaction.business_date"],
                        facts,
                        risk="high",
                    )
                )
                for issue_id, issue_type, required in (
                    ("vat-hi-qualified-entity", "海南享惠主体资格", ["hainan.qualified_entity"]),
                    ("vat-hi-hs-code", "商品HS编码与进口征税目录", ["goods_flow.hs_code"]),
                    ("vat-hi-flow", "一线、二线及岛内流向", ["goods_flow.flow"]),
                    ("vat-hi-use", "进口商品用途与后续处置", ["goods_flow.use"]),
                ):
                    issues.append(_issue(issue_id, issue_type, required, facts, parent=parent, risk="high"))
                issues.append(
                    _issue(
                        "vat-hi-human-review",
                        "海南特殊政策人工审签",
                        [],
                        facts,
                        parent=parent,
                        risk="high",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "vat-hi-ordinary",
                        "海南普通境内业务回落全国增值税规则",
                        ["region.code", "transaction.transaction_type"],
                        facts,
                    )
                )
        elif region == "CN-XJ":
            issues.append(
                _issue(
                    "vat-xj-overlay",
                    "全国规则与新疆覆盖层适用",
                    ["region.code", "transaction.business_date"],
                    facts,
                )
            )
        return issues
