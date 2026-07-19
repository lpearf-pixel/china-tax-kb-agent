from __future__ import annotations

from typing import Any

from .domain import CaseRecord, FactGraph, TaxIssue

MISSING = object()


def _fact(graph: FactGraph, fact_id: str) -> Any:
    item = graph.facts.get(fact_id)
    current = item.current if item else None
    return current.value if current is not None and current.value is not None else MISSING


def _issue(issue_id, issue_type, required, graph, *, risk="low", parent=None, status=None):
    missing = [fact_id for fact_id in required if _fact(graph, fact_id) is MISSING]
    return TaxIssue(
        issue_id=issue_id, tax_type="个人所得税", issue_type=issue_type,
        related_fact_ids=list(required), required_fact_ids=list(required),
        missing_fact_ids=missing, parent_issue_id=parent, risk_level=risk,
        status=status or ("facts_missing" if missing else "identified"),
    )


class PitIssueEngine:
    def identify(self, case: CaseRecord, facts: FactGraph) -> list[TaxIssue]:
        category = _fact(facts, "pit.income_category")
        resident = _fact(facts, "pit.resident_status")
        role = _fact(facts, "pit.taxpayer_role")
        issues = [
            _issue("pit-taxpayer-residency", "居民个人或非居民个人身份", ["pit.resident_status"], facts, risk="high" if resident == "非居民个人" else "low"),
            _issue("pit-income-classification", "个人所得税所得项目分类", ["pit.income_category", "pit.taxpayer_role"], facts),
        ]
        if category == "经营所得":
            issues.extend([
                _issue("pit-business-taxable-income", "经营所得全年应纳税所得额", ["pit.business_taxable_income", "pit.business_other_tax_reduction", "pit.business_prepaid_tax"], facts),
                _issue("pit-business-rate", "经营所得5%至35%税率档位", ["pit.business_taxable_income"], facts),
                _issue("pit-individual-business-half-reduction", "个体工商户不超过200万元部分减半优惠", ["pit.taxpayer_role", "pit.business_taxable_income", "pit.business_other_tax_reduction"], facts, risk="medium"),
            ])
            if _fact(facts, "pit.multiple_business_sources") is True:
                issues.append(_issue("pit-business-multiple-sources", "多处经营所得合并", ["pit.business_income_aggregated"], facts, risk="high"))
            if role == "合伙企业自然人合伙人":
                issues.append(_issue("pit-partnership-allocation", "合伙企业经营所得分配", ["pit.partnership_allocated_income_confirmed"], facts, risk="high"))
        elif category == "劳务报酬":
            issues.extend([
                _issue("pit-labor-withholding", "居民个人劳务报酬预扣预缴", ["pit.labor_gross_income", "pit.labor_withheld_tax", "pit.labor_payer_has_withholding_obligation"], facts),
                _issue("pit-comprehensive-settlement-route", "劳务报酬并入综合所得年度汇算", ["pit.resident_status"], facts, risk="medium"),
            ])
        special = (
            resident == "非居民个人" or _fact(facts, "transaction.cross_border") is True
            or (role == "合伙企业自然人合伙人" and _fact(facts, "pit.partnership_allocated_income_confirmed") is not True)
        )
        if special:
            issues.append(_issue("pit-special-review", "非居民、跨境或合伙分配个人所得税人工复核", [], facts, risk="high", status="manual_review_required"))
        return issues
