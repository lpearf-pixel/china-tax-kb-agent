from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from apps.tax_workbench.models import TaxFacts

from .domain import (
    CaseRecord,
    CaseState,
    Fact,
    FactGraph,
    FactStatus,
    FactVersion,
)


class V6Adapter:
    @staticmethod
    def _fact(
        fact_id: str,
        value,
        now: datetime,
        source: str = "v6_form",
    ) -> Fact:
        return Fact(
            fact_id,
            [
                FactVersion(
                    fact_id,
                    1,
                    value,
                    FactStatus.CONFIRMED,
                    source,
                    now,
                    "user",
                )
            ],
        )

    def to_v7(
        self,
        facts: TaxFacts,
        case_id: str | None = None,
    ) -> tuple[CaseRecord, FactGraph]:
        now = datetime.now(timezone.utc)
        case_id = case_id or f"case-{uuid4().hex[:12]}"
        original_rate = facts.extra.get("original_levy_rate")
        if original_rate in (None, "") and facts.vat_status == "小规模纳税人":
            original_rate = Decimal("0.03")

        values = {
            "case.description": facts.description,
            "case.objective": facts.objective,
            "region.code": facts.region,
            "taxpayer.type": facts.taxpayer_type,
            "taxpayer.vat_status": facts.vat_status,
            "transaction.business_date": facts.business_date,
            "transaction.transaction_type": facts.transaction_type,
            "transaction.sales_amount": facts.amount,
            "transaction.total_sales_same_period": facts.extra.get(
                "total_sales_same_period", facts.amount
            ),
            "transaction.amount_period": facts.amount_period,
            "transaction.amount_tax_inclusive": facts.amount_tax_inclusive,
            "transaction.original_levy_rate": (
                Decimal(str(original_rate)) if original_rate not in (None, "") else None
            ),
            "invoice.need": facts.invoice_need,
            "invoice.need_special_invoice": facts.invoice_need == "专用发票",
            "invoice.waive_exemption": bool(facts.extra.get("waive_exemption", False)),
            "taxpayer.rolling_sales": facts.extra.get("rolling_sales"),
            "transaction.related_party": facts.related_party,
            "transaction.split_signal": bool(facts.extra.get("split_signal"))
            or "分拆" in facts.description,
            "transaction.cross_border": facts.cross_border,
            "hainan.special_scene": facts.hainan_special_scene,
            "goods_flow.hs_code": facts.hs_code or None,
            "hainan.qualified_entity": facts.qualified_entity,
            "goods_flow.flow": facts.extra.get("flow"),
            "goods_flow.use": facts.extra.get("use"),
            "risk.historical_tax": facts.historical_tax,
            "risk.real_estate": facts.real_estate,
            "risk.restructuring": facts.restructuring,
            "risk.tax_audit": facts.tax_audit,
        }
        graph = FactGraph(
            facts={
                key: self._fact(key, value, now)
                for key, value in values.items()
                if value is not None
            },
            nodes={
                "party-main": {
                    "node_id": "party-main",
                    "node_type": "Party",
                    "name": "纳税主体",
                },
                "tx-main": {
                    "node_id": "tx-main",
                    "node_type": "Transaction",
                    "transaction_type": facts.transaction_type,
                },
            },
            edges=[],
            version=1,
        )
        case = CaseRecord(
            case_id=case_id,
            state=CaseState.FACTS_PENDING_CONFIRMATION,
            kb_version="KB-2026.07.17-V5-PILOT-XJ-HI",
            rule_set_version="vat-rules-v1",
            facts_version=1,
            created_at=now,
            updated_at=now,
        )
        return case, graph

    def from_graph(self, graph: FactGraph) -> TaxFacts:
        def value(fact_id: str, default=None):
            fact = graph.facts.get(fact_id)
            current = fact.current if fact else None
            return current.value if current else default

        return TaxFacts.from_dict(
            {
                "business_date": str(value("transaction.business_date", "")),
                "region": value("region.code", ""),
                "taxpayer_type": value("taxpayer.type", ""),
                "vat_status": value("taxpayer.vat_status", "未知"),
                "transaction_type": value("transaction.transaction_type", "其他"),
                "amount": value("transaction.sales_amount"),
                "amount_period": value("transaction.amount_period", "季度"),
                "amount_tax_inclusive": value(
                    "transaction.amount_tax_inclusive", False
                ),
                "invoice_need": value(
                    "invoice.need",
                    "专用发票"
                    if value("invoice.need_special_invoice", False)
                    else "普通发票",
                ),
                "objective": value("case.objective", "合规降负"),
                "description": value("case.description", "持久化案件重算"),
                "related_party": value("transaction.related_party", False),
                "cross_border": value("transaction.cross_border", False),
                "historical_tax": value("risk.historical_tax", False),
                "real_estate": value("risk.real_estate", False),
                "restructuring": value("risk.restructuring", False),
                "tax_audit": value("risk.tax_audit", False),
                "hainan_special_scene": value("hainan.special_scene", False),
                "hs_code": value("goods_flow.hs_code", ""),
                "qualified_entity": value("hainan.qualified_entity", None),
                "flow": value("goods_flow.flow", None),
                "use": value("goods_flow.use", None),
                "total_sales_same_period": value(
                    "transaction.total_sales_same_period", None
                ),
                "original_levy_rate": value(
                    "transaction.original_levy_rate", None
                ),
                "rolling_sales": value("taxpayer.rolling_sales", None),
                "waive_exemption": value("invoice.waive_exemption", False),
            }
        )
