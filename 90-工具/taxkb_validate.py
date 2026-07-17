#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from taxkb_core import extract_wikilinks, iter_markdown, parse_frontmatter, resolve_wikilink

OFFICIAL_DOMAINS = {
    "npc.gov.cn", "www.npc.gov.cn", "flk.npc.gov.cn", "wb.flk.npc.gov.cn",
    "gov.cn", "www.gov.cn", "chinatax.gov.cn", "www.chinatax.gov.cn",
    "fgk.chinatax.gov.cn", "mof.gov.cn", "www.mof.gov.cn", "szs.mof.gov.cn",
    "xzfg.moj.gov.cn", "moj.gov.cn", "www.moj.gov.cn",
}
VALID_STATUSES = {"effective", "partially_effective", "not_yet_effective", "expired", "repealed", "pending_review", "uncertain"}
VALID_TIERS = {"A", "B", "C", "D"}
DATE_FIELDS = ("publish_date", "effective_date", "expiry_date", "provision_valid_from", "provision_valid_to", "verified_at", "captured_at")


def official_domain(host: str) -> bool:
    return host in OFFICIAL_DOMAINS or host.endswith(".chinatax.gov.cn") or host.endswith(".gov.cn")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate V5 tax knowledge Vault metadata, sources and links.")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--report", default="10-法规更新记录/校验报告.md")
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    report = Path(args.report)
    if not report.is_absolute():
        report = vault / report

    errors: list[str] = []
    warnings: list[str] = []
    ids: dict[str, list[str]] = defaultdict(list)
    scanned = 0
    excluded = ("90-工具/", "99-模板/", "99-归档/", "docs/")

    for note in iter_markdown(vault, excluded):
        scanned += 1
        rel = note.relative_to(vault).as_posix()
        text = note.read_text(encoding="utf-8", errors="replace")
        meta, _ = parse_frontmatter(text)
        id_key = None
        if rel.startswith("01-法规原文/"):
            id_key = "document_id"
        elif rel.startswith("02-条款结构/"):
            id_key = "provision_id"
        else:
            for candidate in ("relation_id", "concept_id", "scenario_id", "case_id", "workflow_id", "agent_id", "risk_id"):
                if meta.get(candidate):
                    id_key = candidate
                    break
        if id_key and meta.get(id_key):
            ids[str(meta[id_key])].append(rel)

        if rel.startswith("01-法规原文/") and note.name != "README.md":
            for field in ("document_id", "title", "document_number", "issuer", "document_type", "authority_level", "publish_date", "effective_date", "document_status", "jurisdiction_scope", "evidence_tier", "source_url", "verified_at"):
                if not meta.get(field):
                    errors.append(f"{rel}: 法规卡缺少 `{field}`")
            status = str(meta.get("document_status") or "")
            if status and status not in VALID_STATUSES:
                errors.append(f"{rel}: 无效 document_status `{status}`")
            tier = str(meta.get("evidence_tier") or "").upper()
            if tier and tier not in VALID_TIERS:
                errors.append(f"{rel}: 无效 evidence_tier `{tier}`")
            source = str(meta.get("source_url", ""))
            if source:
                host = urlparse(source).hostname or ""
                if not official_domain(host):
                    warnings.append(f"{rel}: source_url 不是已登记官方域名 `{host}`")

        if rel.startswith("02-条款结构/"):
            for field in ("provision_id", "document_id", "title", "article_number", "provision_valid_from", "provision_status", "jurisdiction_scope", "evidence_tier", "source_note", "verified_at"):
                if not meta.get(field):
                    errors.append(f"{rel}: 条款卡缺少 `{field}`")
            status = str(meta.get("provision_status") or "")
            if status and status not in VALID_STATUSES:
                errors.append(f"{rel}: 无效 provision_status `{status}`")

        for link in extract_wikilinks(text):
            if not resolve_wikilink(vault, link):
                warnings.append(f"{rel}: 无法解析 Wikilink `[[{link}]]`")

        for field in DATE_FIELDS:
            raw = meta.get(field)
            if raw is None or raw == "" or raw == []:
                continue
            value = str(raw)
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                errors.append(f"{rel}: {field} 格式应为 YYYY-MM-DD，实际 `{value}`")

    for unique_id, paths in ids.items():
        if len(paths) > 1:
            errors.append(f"重复 ID `{unique_id}`: {', '.join(paths)}")

    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Vault 校验报告", "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 扫描 Markdown：{scanned}",
        f"- 错误：{len(errors)}",
        f"- 警告：{len(warnings)}", "",
        "## 错误", "",
    ]
    lines += [f"- {x}" for x in errors] or ["- 无"]
    lines += ["", "## 警告", ""]
    lines += [f"- {x}" for x in warnings] or ["- 无"]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"validation: {len(errors)} errors, {len(warnings)} warnings -> {report}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
