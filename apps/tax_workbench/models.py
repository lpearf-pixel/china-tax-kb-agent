from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

REGIONS = {"CN", "CN-XJ", "CN-HI"}
TAXPAYER_TYPES = {"自然人", "个体工商户", "企业", "其他组织"}
VAT_STATUSES = {"小规模纳税人", "一般纳税人", "未知"}
TRANSACTION_TYPES = {"货物", "服务", "无形资产", "不动产", "进口货物", "其他"}
AMOUNT_PERIODS = {"月", "季度", "单次", "年度"}
INVOICE_NEEDS = {"普通发票", "专用发票", "不确定", "无需发票"}
EVIDENCE_ROLES = ("support", "limitation", "exclusion", "historical", "local", "conflict")


def _bool(value: Any, default: bool | None = False) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y", "是"}:
        return True
    if raw in {"0", "false", "no", "n", "否"}:
        return False
    return default


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


@dataclass(slots=True)
class TaxFacts:
    business_date: str = ""
    region: str = ""
    taxpayer_type: str = ""
    vat_status: str = ""
    transaction_type: str = ""
    amount: Decimal | None = None
    amount_period: str = ""
    amount_tax_inclusive: bool = False
    invoice_need: str = ""
    objective: str = ""
    description: str = ""
    related_party: bool = False
    cross_border: bool = False
    historical_tax: bool = False
    real_estate: bool = False
    restructuring: bool = False
    tax_audit: bool = False
    hainan_special_scene: bool = False
    hs_code: str = ""
    qualified_entity: bool | None = None
    resident_qualification: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaxFacts":
        known = {item.name for item in cls.__dataclass_fields__.values()}
        values = {key: data.get(key) for key in known if key != "extra"}
        values["amount"] = _decimal(data.get("amount"))
        for name in ("amount_tax_inclusive", "related_party", "cross_border", "historical_tax", "real_estate", "restructuring", "tax_audit", "hainan_special_scene"):
            values[name] = bool(_bool(data.get(name), False))
        values["qualified_entity"] = _bool(data.get("qualified_entity"), None)
        values["resident_qualification"] = _bool(data.get("resident_qualification"), None)
        for name in ("business_date", "region", "taxpayer_type", "vat_status", "transaction_type", "amount_period", "invoice_need", "objective", "description", "hs_code"):
            values[name] = str(data.get(name) or "").strip()
        values["extra"] = {key: value for key, value in data.items() if key not in known}
        return cls(**values)

    def validate(self) -> list[str]:
        errors: list[str] = []
        try:
            date.fromisoformat(self.business_date)
        except ValueError:
            errors.append("business_date 必须是 YYYY-MM-DD")
        if self.region not in REGIONS:
            errors.append("region 必须是 CN、CN-XJ 或 CN-HI")
        if self.taxpayer_type not in TAXPAYER_TYPES:
            errors.append("taxpayer_type 必须明确自然人、个体工商户、企业或其他组织")
        if self.vat_status not in VAT_STATUSES:
            errors.append("vat_status 必须明确小规模纳税人、一般纳税人或未知")
        if self.transaction_type not in TRANSACTION_TYPES:
            errors.append("transaction_type 必须明确货物、服务、无形资产、不动产、进口货物或其他")
        if self.amount is None:
            errors.append("amount 必须是有效金额")
        elif self.amount < 0:
            errors.append("amount 不能为负数")
        if self.amount_period not in AMOUNT_PERIODS:
            errors.append("amount_period 必须是月、季度、单次或年度")
        if self.invoice_need not in INVOICE_NEEDS:
            errors.append("invoice_need 必须明确普通发票、专用发票、不确定或无需发票")
        if not self.objective:
            errors.append("objective 必须明确规划目标")
        if not self.description:
            errors.append("description 必须说明真实业务")
        return errors

    def missing_facts(self) -> list[str]:
        missing: list[str] = []
        hainan_gate = self.region == "CN-HI" and (self.hainan_special_scene or self.transaction_type == "进口货物" or self.cross_border)
        if hainan_gate:
            if not self.hs_code:
                missing.append("商品 HS 编码")
            if self.qualified_entity is None:
                missing.append("海南自贸港享惠主体资格")
            if "flow" not in self.extra:
                missing.append("货物一线/二线/岛内流向")
            if "use" not in self.extra:
                missing.append("进口商品用途与后续处置")
        if self.invoice_need == "不确定":
            missing.append("客户发票类型要求")
        if self.vat_status == "未知":
            missing.append("增值税纳税人登记身份")
        return missing

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["amount"] = str(self.amount) if self.amount is not None else None
        return payload


@dataclass(slots=True)
class EvidenceItem:
    path: str
    title: str
    document_number: str = ""
    article: str = ""
    excerpt: str = ""
    score: float = 0.0
    source_url: str = ""
    jurisdiction_scope: str = "CN"
    evidence_tier: str = "A"
    role: str = "support"
    document_id: str = ""
    provision_id: str = ""
    valid_from: str = ""
    valid_to: str = ""
    status: str = "effective"
    score_breakdown: dict[str, float] = field(default_factory=dict)
    match_reasons: list[str] = field(default_factory=list)
    _retrieval_trace: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        trace = payload.pop("_retrieval_trace", {})
        if trace:
            payload["retrieval_trace"] = trace
        return payload


@dataclass(slots=True)
class SchemeOption:
    name: str
    summary: str
    actions: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    estimated_tax: str = "待根据完整成本、进项和计税依据测算"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanningResult:
    initial_conclusion: str
    applicable_conditions: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    explanation: str = ""
    regional_application: str = ""
    schemes: list[SchemeOption] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    human_review_required: bool = False
    kb_version: str = "KB-2026.07.17-V5-PILOT-XJ-HI"
    verified_at: str = "2026-07-18"
    disclaimer: str = "本结果为法规检索和税务规划草案，不替代主管税务机关、注册税务师或律师的正式意见。"
    case_id: str = ""
    case_state: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)
    rule_trace: list[dict[str, Any]] = field(default_factory=list)
    calculations: list[dict[str, Any]] = field(default_factory=list)
    scenario_scores: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    evidence_groups: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    retrieval_trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for row in payload.get("evidence", []):
            row.pop("_retrieval_trace", None)
            row.pop("retrieval_trace", None)
        if not self.evidence_groups:
            groups = {role: [] for role in EVIDENCE_ROLES}
            for item in self.evidence:
                public = item.to_dict()
                public.pop("retrieval_trace", None)
                groups.setdefault(item.role, []).append(public)
            payload["evidence_groups"] = groups
        if not self.retrieval_trace:
            payload["retrieval_trace"] = next((item._retrieval_trace for item in self.evidence if item._retrieval_trace), {})
        return payload
