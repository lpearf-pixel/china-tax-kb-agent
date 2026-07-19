from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import EVIDENCE_ROLES, PlanningResult, TaxFacts

ROLE_LABELS = {
    "support": "支持证据",
    "limitation": "限制与适用条件",
    "exclusion": "排除与不适用证据",
    "historical": "历史与已失效证据",
    "local": "地方覆盖证据",
    "conflict": "冲突与待复核证据",
}


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def _value(value: Any) -> str:
    if isinstance(value, dict) and value.get("__type__") in {"decimal", "date", "datetime"}:
        return str(value.get("value", ""))
    return "" if value is None else str(value)


def _status_label(raw: str) -> str:
    return {
        "applicable": "适用",
        "not_applicable": "不适用",
        "insufficient_facts": "事实不足",
        "conflict": "冲突",
        "manual_review_required": "人工复核",
    }.get(raw, raw)


def json_score(components: dict[str, Any]) -> str:
    return "；".join(f"{key}={value}" for key, value in components.items()) if components else "无"


def _groups(result: PlanningResult) -> dict[str, list[dict[str, Any]]]:
    if result.evidence_groups:
        return {role: list(result.evidence_groups.get(role, [])) for role in EVIDENCE_ROLES}
    groups = {role: [] for role in EVIDENCE_ROLES}
    for item in result.evidence:
        groups.setdefault(item.role, []).append(item.to_dict())
    return groups


def _trace(result: PlanningResult) -> dict[str, Any]:
    if result.retrieval_trace:
        return result.retrieval_trace
    return next((item._retrieval_trace for item in result.evidence if item._retrieval_trace), {})


def _render_evidence(lines: list[str], result: PlanningResult) -> None:
    lines += ["## 法规证据包", ""]
    for role in EVIDENCE_ROLES:
        rows = _groups(result).get(role, [])
        lines += [f"### {ROLE_LABELS[role]}", ""]
        if not rows:
            lines += ["- 无", ""]
            continue
        for index, item in enumerate(rows, 1):
            path = str(item.get("path") or "")
            target = path[:-3] if path.endswith(".md") else path
            title = str(item.get("title") or Path(path).stem)
            labels = "，".join(str(value) for value in (item.get("document_number"), item.get("article")) if value)
            lines.append(f"{index}. [[{target}|{title}]]" + (f"（{labels}）" if labels else ""))
            lines.append(
                f"   - 状态：{item.get('status', '')}｜地域：{item.get('jurisdiction_scope', '')}"
                f"｜等级：{item.get('evidence_tier', '')}｜最终分：{item.get('score', 0)}"
            )
            if item.get("valid_from") or item.get("valid_to"):
                lines.append(f"   - 有效区间：{item.get('valid_from') or '未注明'} 至 {item.get('valid_to') or '持续有效'}")
            if item.get("match_reasons"):
                lines.append(f"   - 命中原因：{'；'.join(item['match_reasons'][:8])}")
            if item.get("score_breakdown"):
                lines.append(f"   - 评分构成：{json_score(item['score_breakdown'])}")
            excerpt = str(item.get("excerpt") or "").replace("\n", " ")[:300]
            if excerpt:
                lines.append(f"   - 摘要：{excerpt}")
        lines.append("")


def _render_retrieval_trace(lines: list[str], result: PlanningResult) -> None:
    trace = _trace(result)
    lines += ["## 检索审计轨迹", ""]
    if not trace:
        lines += ["- 无", ""]
        return
    lines += [
        f"- 检索提供方：`{trace.get('provider', '')}`",
        f"- 门禁前分块：{trace.get('documents_before_gate', 0)}",
        f"- 门禁后分块：{trace.get('documents_after_gate', 0)}",
        f"- 初始候选：{trace.get('candidate_count', 0)}",
        f"- 关系扩展：{trace.get('relation_expanded_count', 0)}",
        f"- 最终证据：{trace.get('selected_count', 0)}",
    ]
    if trace.get("provider_errors"):
        lines.append(f"- Provider 回退：{'；'.join(trace['provider_errors'])}")
    plan = trace.get("plan") or {}
    if plan:
        lines += ["", "### 子查询", ""]
        stats = trace.get("query_stats") or {}
        for query in plan.get("queries", []):
            query_id = query.get("query_id", "")
            row = stats.get(query_id, {})
            lines.append(
                f"- `{query_id}` [{query.get('role', '')}] {query.get('text', '')}"
                f"｜门禁后 {row.get('gated', 0)}｜BM25 {row.get('bm25', 0)}｜向量 {row.get('vector', 0)}"
            )
    lines.append("")


def render_markdown(facts: TaxFacts, result: PlanningResult) -> str:
    lines = [
        "---",
        f'title: "税务规划会话_{facts.business_date}_{facts.region}"',
        "type: planning_session",
        f'case_id: "{result.case_id}"',
        f'case_state: "{result.case_state}"',
        f'business_date: "{facts.business_date}"',
        f'jurisdiction_scope: "{facts.region}"',
        f'taxpayer_type: "{facts.taxpayer_type}"',
        f'analyzed_tax_types: "{",".join(facts.requested_tax_types)}"',
        f'kb_version: "{result.kb_version}"',
        f'verified_at: "{result.verified_at}"',
        f'human_review_required: {str(result.human_review_required).lower()}',
        "---", "", "# 税务规划会话", "",
        "## 案件状态", "",
        f"- 案件编号：`{result.case_id or '未持久化'}`",
        f"- 当前状态：`{result.case_state or 'stateless_analysis'}`",
        f"- 分析税种：{', '.join(facts.requested_tax_types)}",
        f"- 人工审签：{'必须' if result.human_review_required else '当前未强制'}", "",
        "## 初步结论", "", result.initial_conclusion, "",
        "## 适用前提", "", _bullet(result.applicable_conditions), "",
        "## 原始事实", "",
        f"- 业务描述：{facts.description}",
        f"- 规划目标：{facts.objective}",
        f"- 金额：{facts.amount}（{'含税' if facts.amount_tax_inclusive else '未声明含税'}）",
        f"- 企业实体形式：{facts.entity_form or '未选择'}",
        f"- 企业所得税居民身份：{facts.cit_resident_status or '未选择'}",
        f"- 会计利润：{facts.cit_accounting_profit if facts.cit_accounting_profit is not None else '未提供'}",
        f"- 个人所得税所得类别：{facts.pit_income_category or '未选择'}",
        f"- 个人所得税居民身份：{facts.pit_resident_status or '未选择'}",
        f"- 个人所得税纳税角色：{facts.pit_taxpayer_role or '未选择'}",
        f"- 经营所得应纳税所得额：{facts.pit_business_taxable_income if facts.pit_business_taxable_income is not None else '未提供'}",
        f"- 劳务报酬收入：{facts.pit_labor_gross_income if facts.pit_labor_gross_income is not None else '未提供'}",
        f"- 支付方扣缴义务：{'已确认' if facts.pit_labor_payer_has_withholding_obligation is True else '未确认' if facts.pit_labor_payer_has_withholding_obligation is None else '否'}",
        f"- 是否关联交易：{'是' if facts.related_party else '否'}", "",
        "## 税务议题树", "",
    ]
    if result.issues:
        for issue in result.issues:
            prefix = "  -" if issue.get("parent_issue_id") else "-"
            lines.append(
                f"{prefix} `{issue.get('issue_id', '')}` [{issue.get('tax_type', '')}] {issue.get('issue_type', '')}"
                f"｜风险：{issue.get('risk_level', 'low')}｜状态：{issue.get('status', '')}"
            )
            if issue.get("missing_fact_ids"):
                lines.append(f"    - 缺失事实：{', '.join(issue['missing_fact_ids'])}")
    else:
        lines.append("- 无")
    lines.append("")
    _render_evidence(lines, result)
    _render_retrieval_trace(lines, result)

    lines += ["## 规则判断轨迹", ""]
    for evaluation in result.rule_trace or []:
        lines += [
            f"### `{evaluation.get('rule_id', '')}`｜{_status_label(str(evaluation.get('status', ''))) }", "",
            f"- 输出：`{evaluation.get('outcome', '')}` = `{_value(evaluation.get('value'))}`",
            f"- 优先级：{evaluation.get('priority', 0)}",
        ]
        if evaluation.get("missing_fact_ids"):
            lines.append(f"- 缺失事实：{', '.join(evaluation['missing_fact_ids'])}")
        lines.append("")
    if not result.rule_trace:
        lines += ["- 无", ""]

    lines += ["## 税额计算与现金流", ""]
    for calculation in result.calculations or []:
        lines += [
            f"### `{calculation.get('calculation_id', '')}`｜{calculation.get('tax_type', '')}", "",
            f"- 状态：`{calculation.get('status', '')}`",
            f"- 计税基础：{_value(calculation.get('taxable_amount'))}",
            f"- 税额：{_value(calculation.get('tax_amount'))}",
            f"- 应补退/留抵候选：{_value(calculation.get('payable_or_credit'))}",
            f"- 公式：{calculation.get('formula', '')}",
            f"- 使用规则：{', '.join(calculation.get('rule_ids', [])) or '无'}",
        ]
        if calculation.get("tax_type") == "个人所得税" and calculation.get("status") == "conditional_determinate":
            lines.append("- 重要边界：当前金额属于预扣候选，不等于年度最终税负；居民个人年度终了后仍需按规定汇算。")
        if calculation.get("missing_fact_ids"):
            lines.append(f"- 缺失输入：{', '.join(calculation['missing_fact_ids'])}")
        for event in calculation.get("cashflow_events", []):
            lines.append(f"- 现金流事件：{event.get('date', '')}｜{event.get('type', '')}｜{event.get('amount', '')}")
        lines.append("")
    if not result.calculations:
        lines += ["- 无", ""]

    lines += [
        "## 通俗解释", "", result.explanation, "",
        "## 地域适用情况", "", result.regional_application, "",
        "## 税务方案", "",
    ]
    for index, scheme in enumerate(result.schemes):
        score = result.scenario_scores[index] if index < len(result.scenario_scores) else {}
        scenario_id = score.get("scenario_id", f"scenario-{index + 1}")
        lines += [
            f"### {scheme.name}", "", scheme.summary, "",
            f"- 方案编号：`{scenario_id}`",
            "- 方案评分 / 综合评分：" + str(score.get("total_score", "未评分")),
            f"- 评分构成：{json_score(score.get('components', {}))}",
            "- 税种分项：",
        ]
        breakdown = dict(getattr(scheme, "tax_breakdown", {}) or {})
        lines.extend(f"  - {tax_type}：{amount}" for tax_type, amount in breakdown.items())
        if not breakdown:
            lines.append("  - 未生成分项")
        lines += [
            f"- 综合税负：{scheme.estimated_tax}", "",
            "**执行动作**", _bullet(scheme.actions), "",
            "**预期价值**", _bullet(scheme.benefits), "",
            "**风险边界**", _bullet(scheme.risks), "",
            "**所需资料**", _bullet(scheme.required_documents), "",
        ]

    lines += [
        "## 风险与待确认事项", "", _bullet(result.risks), "",
        "### 待补事实", "", _bullet(result.missing_facts), "",
        "## 信息时效", "",
        f"- 知识库版本：`{result.kb_version}`",
        f"- 法规核验日期：`{result.verified_at}`", "",
        "## 免责声明", "", result.disclaimer, "",
    ]
    return "\n".join(lines)


def _safe_name(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", text).strip("-")
    return cleaned[:40] or "税务规划"


def save_session(vault: Path, facts: TaxFacts, result: PlanningResult) -> Path:
    root = Path(vault).resolve() / "16-交互工作台" / "会话记录"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    identity = result.case_id or uuid4().hex[:6]
    path = root / f"{stamp}_{_safe_name(facts.description)}_{identity}.md"
    path.write_text(render_markdown(facts, result), encoding="utf-8")
    return path
