from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import PlanningResult, TaxFacts


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def _value(value: Any) -> str:
    if isinstance(value, dict) and value.get("__type__") in {
        "decimal",
        "date",
        "datetime",
    }:
        return str(value.get("value", ""))
    if value is None:
        return ""
    return str(value)


def _status_label(raw: str) -> str:
    return {
        "applicable": "适用",
        "not_applicable": "不适用",
        "insufficient_facts": "事实不足",
        "conflict": "冲突",
        "manual_review_required": "人工复核",
    }.get(raw, raw)


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
        f'vat_status: "{facts.vat_status}"',
        f'kb_version: "{result.kb_version}"',
        f'verified_at: "{result.verified_at}"',
        f'human_review_required: {str(result.human_review_required).lower()}',
        "---",
        "",
        "# 税务规划会话",
        "",
        "## 案件状态",
        "",
        f"- 案件编号：`{result.case_id or '未持久化'}`",
        f"- 当前状态：`{result.case_state or 'stateless_analysis'}`",
        f"- 人工审签：{'必须' if result.human_review_required else '当前未强制'}",
        "",
        "## 初步结论",
        "",
        result.initial_conclusion,
        "",
        "## 适用前提",
        "",
        _bullet(result.applicable_conditions),
        "",
        "## 原始事实",
        "",
        f"- 业务描述：{facts.description}",
        f"- 规划目标：{facts.objective}",
        f"- 金额：{facts.amount}（{'含税' if facts.amount_tax_inclusive else '未声明含税'}）",
        f"- 是否关联交易：{'是' if facts.related_party else '否'}",
        "",
        "## 税务议题树",
        "",
    ]
    if result.issues:
        for issue in result.issues:
            prefix = "  -" if issue.get("parent_issue_id") else "-"
            lines.append(
                f"{prefix} `{issue.get('issue_id', '')}` {issue.get('issue_type', '')}"
                f"｜风险：{issue.get('risk_level', 'low')}"
                f"｜状态：{issue.get('status', '')}"
            )
            if issue.get("missing_fact_ids"):
                lines.append(
                    f"    - 缺失事实：{', '.join(issue['missing_fact_ids'])}"
                )
    else:
        lines.append("- 无")

    lines += ["", "## 法规依据", ""]
    if result.evidence:
        for index, item in enumerate(result.evidence, 1):
            label = "，".join(x for x in (item.document_number, item.article) if x)
            target = item.path[:-3] if item.path.endswith(".md") else item.path
            lines.append(
                f"{index}. [[{target}|{item.title}]]"
                + (f"（{label}）" if label else "")
            )
            if item.excerpt:
                lines.append(
                    f"   - 证据摘要：{item.excerpt.replace(chr(10), ' ')[:240]}"
                )
    else:
        lines.append("1. 未检索到足够的 A 级有效法规依据。")

    lines += ["", "## 规则判断轨迹", ""]
    if result.rule_trace:
        for evaluation in result.rule_trace:
            lines.append(
                f"### `{evaluation.get('rule_id', '')}`｜"
                f"{_status_label(str(evaluation.get('status', '')))}"
            )
            lines.append("")
            lines.append(
                f"- 输出：`{evaluation.get('outcome', '')}` = "
                f"`{_value(evaluation.get('value'))}`"
            )
            lines.append(f"- 优先级：{evaluation.get('priority', 0)}")
            if evaluation.get("missing_fact_ids"):
                lines.append(
                    f"- 缺失事实：{', '.join(evaluation['missing_fact_ids'])}"
                )
            for trace in evaluation.get("trace", [])[:12]:
                if trace.get("reason"):
                    lines.append(f"- 轨迹：{trace.get('reason')}")
                elif trace.get("fact"):
                    lines.append(
                        f"- `{trace.get('fact')}` {trace.get('operator')} "
                        f"`{_value(trace.get('expected'))}` → "
                        f"`{_value(trace.get('actual'))}`，"
                        f"结果：{trace.get('result', 'missing')}"
                    )
            lines.append("")
    else:
        lines.append("- 无")

    lines += ["## 税额计算与现金流", ""]
    if result.calculations:
        for calculation in result.calculations:
            lines += [
                f"### `{calculation.get('calculation_id', '')}`",
                "",
                f"- 状态：`{calculation.get('status', '')}`",
                f"- 计税销售额：{_value(calculation.get('taxable_amount'))}",
                f"- 税额：{_value(calculation.get('tax_amount'))}",
                f"- 应纳或留抵：{_value(calculation.get('payable_or_credit'))}",
                f"- 公式：{calculation.get('formula', '')}",
                f"- 使用规则：{', '.join(calculation.get('rule_ids', [])) or '无'}",
            ]
            if calculation.get("missing_fact_ids"):
                lines.append(
                    f"- 缺失输入：{', '.join(calculation['missing_fact_ids'])}"
                )
            for event in calculation.get("cashflow_events", []):
                lines.append(
                    f"- 现金流事件：{event.get('date', '')}｜"
                    f"{event.get('type', '')}｜{event.get('amount', '')}"
                )
            lines.append("")
    else:
        lines.append("- 无")

    lines += [
        "## 通俗解释",
        "",
        result.explanation,
        "",
        "## 地域适用情况",
        "",
        result.regional_application,
        "",
        "## 税务方案",
        "",
    ]
    scores = {item.get("scenario_id"): item for item in result.scenario_scores}
    for scheme, calculation in zip(result.schemes, result.calculations):
        scenario_id = f"scenario-{calculation.get('calculation_id', '')}"
        score = scores.get(scenario_id, {})
        lines += [
            f"### {scheme.name}",
            "",
            scheme.summary,
            "",
            f"- 方案编号：`{scenario_id}`",
            f"- 综合评分：{score.get('total_score', '未评分')}",
            f"- 评分构成：{json_score(score.get('components', {}))}",
            "",
            "**执行动作**",
            _bullet(scheme.actions),
            "",
            "**预期价值**",
            _bullet(scheme.benefits),
            "",
            "**风险边界**",
            _bullet(scheme.risks),
            "",
            "**所需资料**",
            _bullet(scheme.required_documents),
            "",
            f"**税负提示**：{scheme.estimated_tax}",
            "",
        ]

    lines += [
        "## 风险与待确认事项",
        "",
        _bullet(result.risks),
        "",
        "### 待补事实",
        "",
        _bullet(result.missing_facts),
        "",
        "## 信息时效",
        "",
        f"- 知识库版本：`{result.kb_version}`",
        f"- 法规核验日期：`{result.verified_at}`",
        "",
        "## 免责声明",
        "",
        result.disclaimer,
        "",
    ]
    return "\n".join(lines)


def json_score(components: dict[str, Any]) -> str:
    if not components:
        return "无"
    return "；".join(f"{key}={value}" for key, value in components.items())


def _safe_name(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", text).strip("-")
    return cleaned[:40] or "税务规划"


def save_session(vault: Path, facts: TaxFacts, result: PlanningResult) -> Path:
    root = Path(vault).resolve() / "16-交互工作台" / "会话记录"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    identity = result.case_id or uuid4().hex[:6]
    filename = f"{stamp}_{_safe_name(facts.description)}_{identity}.md"
    path = root / filename
    path.write_text(render_markdown(facts, result), encoding="utf-8")
    return path
