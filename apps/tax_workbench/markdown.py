from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .models import PlanningResult, TaxFacts


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def render_markdown(facts: TaxFacts, result: PlanningResult) -> str:
    lines = [
        "---",
        f'title: "税务规划会话_{facts.business_date}_{facts.region}"',
        "type: planning_session",
        f'business_date: "{facts.business_date}"',
        f'jurisdiction_scope: "{facts.region}"',
        f'taxpayer_type: "{facts.taxpayer_type}"',
        f'vat_status: "{facts.vat_status}"',
        f'kb_version: "{result.kb_version}"',
        f'verified_at: "{result.verified_at}"',
        f'human_review_required: {str(result.human_review_required).lower()}',
        "---", "",
        "# 税务规划会话", "",
        "## 初步结论", "", result.initial_conclusion, "",
        "## 适用前提", "", _bullet(result.applicable_conditions), "",
        "## 原始事实", "",
        f"- 业务描述：{facts.description}",
        f"- 规划目标：{facts.objective}",
        f"- 金额：{facts.amount}（{'含税' if facts.amount_tax_inclusive else '未声明含税'}）",
        f"- 是否关联交易：{'是' if facts.related_party else '否'}", "",
        "## 法规依据", "",
    ]
    if result.evidence:
        for index, item in enumerate(result.evidence, 1):
            label = "，".join(x for x in (item.document_number, item.article) if x)
            lines.append(f"{index}. [[{item.path[:-3] if item.path.endswith('.md') else item.path}|{item.title}]]" + (f"（{label}）" if label else ""))
            if item.excerpt:
                lines.append(f"   - 证据摘要：{item.excerpt.replace(chr(10), ' ')[:240]}")
    else:
        lines.append("1. 未检索到足够的 A 级有效法规依据。")
    lines += ["", "## 通俗解释", "", result.explanation, "", "## 地域适用情况", "", result.regional_application, "", "## 税务方案", ""]
    for scheme in result.schemes:
        lines += [
            f"### {scheme.name}", "", scheme.summary, "",
            "**执行动作**", _bullet(scheme.actions), "",
            "**预期价值**", _bullet(scheme.benefits), "",
            "**风险边界**", _bullet(scheme.risks), "",
            "**所需资料**", _bullet(scheme.required_documents), "",
            f"**税负提示**：{scheme.estimated_tax}", "",
        ]
    lines += [
        "## 风险与待确认事项", "",
        _bullet(result.risks), "",
        "### 待补事实", "", _bullet(result.missing_facts), "",
        f"### 人工审签：{'必须' if result.human_review_required else '当前未强制，但正式执行前仍应复核'}", "",
        "## 信息时效", "",
        f"- 知识库版本：`{result.kb_version}`",
        f"- 法规核验日期：`{result.verified_at}`",
        "", "## 免责声明", "", result.disclaimer, "",
    ]
    return "\n".join(lines)


def _safe_name(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", text).strip("-")
    return cleaned[:40] or "税务规划"


def save_session(vault: Path, facts: TaxFacts, result: PlanningResult) -> Path:
    root = Path(vault).resolve() / "16-交互工作台" / "会话记录"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{stamp}_{_safe_name(facts.description)}_{uuid4().hex[:6]}.md"
    path = root / filename
    path.write_text(render_markdown(facts, result), encoding="utf-8")
    return path
