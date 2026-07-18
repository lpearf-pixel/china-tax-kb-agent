from __future__ import annotations

from typing import Any

from .models import QueryPlan, QuerySpec


def _value(obj: Any, name: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compact(*parts: Any) -> str:
    return " ".join(str(part).strip() for part in parts if part not in (None, "", False)).strip()[:500]


class QueryPlanner:
    HISTORICAL_TERMS = ("历史", "当时", "废止", "失效", "旧规", "补税", "以前", "2023", "2024", "2025")

    def plan(self, facts: Any, issues: list[Any] | None = None) -> QueryPlan:
        description = str(_value(facts, "description", ""))
        region = str(_value(facts, "region", "CN"))
        valid_on = str(_value(facts, "business_date", ""))
        taxpayer = str(_value(facts, "taxpayer_type", ""))
        vat_status = str(_value(facts, "vat_status", ""))
        transaction = str(_value(facts, "transaction_type", ""))
        period = str(_value(facts, "amount_period", ""))
        invoice = str(_value(facts, "invoice_need", ""))
        objective = str(_value(facts, "objective", ""))
        hs_code = str(_value(facts, "hs_code", ""))
        related = bool(_value(facts, "related_party", False))
        cross_border = bool(_value(facts, "cross_border", False))
        historical_flag = bool(_value(facts, "historical_tax", False))
        hainan_special = bool(_value(facts, "hainan_special_scene", False))
        issue_terms: list[str] = []
        for issue in issues or []:
            issue_terms.extend([str(_value(issue, "issue_type", "")), str(_value(issue, "risk_level", ""))])
        historical_requested = historical_flag or any(term in description for term in self.HISTORICAL_TERMS)
        region_name = {"CN-XJ": "新疆", "CN-HI": "海南", "CN": "全国"}.get(region, region)
        base = _compact(description, taxpayer, vat_status, transaction, period, objective, region_name, *issue_terms)
        version_statuses = ["effective", "partially_effective", "pending_review", "uncertain"]
        if historical_requested:
            version_statuses.extend(["repealed", "expired"])
        queries = [
            QuerySpec("q-main", "main", base, optional_terms=(transaction, region_name)),
            QuerySpec("q-eligibility", "eligibility", _compact(base, "纳税人身份 起征点 免税 3%减按1% 一般纳税人登记"), optional_terms=("起征点", "1%", "登记")),
            QuerySpec("q-limitation", "limitation", _compact(base, "适用条件 必须 核验 同一计税期间 全部销售额", invoice, "放弃免税 专用发票"), optional_terms=("条件", "必须", "核验")),
            QuerySpec("q-exclusion", "exclusion", _compact(base, "不适用 除外 排除 不得", "销售出租不动产 转让土地使用权 关联分拆" if related else "销售出租不动产 转让土地使用权"), optional_terms=("不适用", "除外", "排除")),
            QuerySpec("q-version", "version", _compact(base, valid_on, "生效日期 有效期 延期 修改 废止 替代 待复核 效力争议"), optional_terms=("有效期", "废止", "替代", "待复核"), statuses=tuple(version_statuses)),
        ]
        if region in {"CN-XJ", "CN-HI"}:
            local_terms = "全国规则 地方覆盖 上位法 执行口径"
            if region == "CN-HI":
                local_terms += " 海南自贸港 普通境内业务"
            queries.append(QuerySpec("q-local", "local", _compact(base, local_terms), optional_terms=(region_name, "覆盖")))
        if region == "CN-HI" and (hainan_special or transaction == "进口货物" or cross_border):
            special_text = _compact(base, "海南自贸港 一线 二线 进口 零关税 普通税制基线", "享惠主体 HS编码 进口征税商品目录 贸易救济 货物流向 用途 后续处置 人工复核", hs_code)
            queries[1] = QuerySpec("q-eligibility", "eligibility", special_text, optional_terms=("享惠主体", "HS编码", "零关税"))
            queries[2] = QuerySpec("q-limitation", "limitation", _compact(special_text, "资格条件 监管资料 报关 物流 用途 台账"))
            queries[3] = QuerySpec("q-exclusion", "exclusion", _compact(special_text, "进口征税目录 不符合资格 不得享受 转售 贸易救济"))
        return QueryPlan(jurisdiction=region, valid_on=valid_on, tax_type=None if transaction == "进口货物" else "增值税", queries=queries, historical_requested=historical_requested)
