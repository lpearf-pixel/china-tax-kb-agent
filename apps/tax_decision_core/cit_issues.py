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
    risk: str = "low",
    parent: str | None = None,
    status: str | None = None,
) -> TaxIssue:
    missing = [fact_id for fact_id in required if _fact(graph, fact_id) is MISSING]
    return TaxIssue(
        issue_id=issue_id,
        tax_type="企业所得税",
        issue_type=issue_type,
        related_fact_ids=list(required),
        required_fact_ids=list(required),
        missing_fact_ids=missing,
        parent_issue_id=parent,
        risk_level=risk,
        status=status or ("facts_missing" if missing else "identified"),
    )


class CitIssueEngine:
    """Build a deterministic enterprise-income-tax issue tree."""

    def identify(self, case: CaseRecord, facts: FactGraph) -> list[TaxIssue]:
        entity_form = _fact(facts, "cit.entity_form")
        resident_status = _fact(facts, "cit.resident_status")
        excluded = entity_form in {"个人独资企业", "合伙企业"}

        issues: list[TaxIssue] = [
            _issue(
                "cit-taxpayer-scope",
                "是否属于企业所得税纳税人",
                ["cit.entity_form"],
                facts,
                status="not_applicable" if excluded else None,
            ),
            _issue(
                "cit-resident-status",
                "居民企业或非居民企业身份",
                ["cit.resident_status"],
                facts,
                risk="high" if resident_status == "非居民企业" else "low",
            ),
        ]

        if excluded:
            return issues

        issues.extend(
            [
                _issue(
                    "cit-taxable-income",
                    "会计利润与纳税调整形成应纳税所得额",
                    [
                        "cit.accounting_profit",
                        "cit.adjustment_increase",
                        "cit.adjustment_decrease",
                        "cit.loss_carryforward",
                    ],
                    facts,
                ),
                _issue(
                    "cit-loss-carryforward",
                    "以前年度亏损弥补",
                    ["cit.loss_carryforward"],
                    facts,
                    risk="medium",
                ),
                _issue(
                    "cit-small-low-profit",
                    "小型微利企业资格与阶段性优惠",
                    [
                        "cit.estimated_taxable_income",
                        "cit.employee_count_avg",
                        "cit.asset_total_avg",
                        "cit.restricted_industry",
                        "cit.has_unincorporated_branches",
                    ],
                    facts,
                    risk="medium",
                ),
                _issue(
                    "cit-tax-credit-prepaid",
                    "税额抵免与已预缴税额",
                    ["cit.tax_credit", "cit.prepaid_tax"],
                    facts,
                ),
            ]
        )

        special = (
            resident_status == "非居民企业"
            or _fact(facts, "transaction.cross_border") is True
            or _fact(facts, "transaction.related_party") is True
            or _fact(facts, "risk.restructuring") is True
            or _fact(facts, "risk.real_estate") is True
        )
        if special:
            issues.append(
                _issue(
                    "cit-special-review",
                    "非居民、跨境、关联、重组或房地产企业所得税人工复核",
                    [],
                    facts,
                    risk="high",
                    status="manual_review_required",
                )
            )
        return issues
