#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from taxkb_core import bm25_rank, filter_docs


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a dependency-free metadata-aware BM25 regression benchmark.")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--chunks", default="90-工具/output/chunks.jsonl")
    parser.add_argument("--cases", default="11-问题测试集/eval_cases.jsonl")
    parser.add_argument("--report", default="11-问题测试集/最近评测报告.md")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    chunks_path = vault / args.chunks if not Path(args.chunks).is_absolute() else Path(args.chunks)
    cases_path = vault / args.cases if not Path(args.cases).is_absolute() else Path(args.cases)
    report_path = vault / args.report if not Path(args.report).is_absolute() else Path(args.report)
    all_docs = load_jsonl(chunks_path)
    cases = load_jsonl(cases_path)

    hits = 0
    reciprocal = 0.0
    details = []
    for case in cases:
        docs = filter_docs(
            all_docs,
            jurisdiction=case.get("jurisdiction"),
            valid_on=case.get("valid_on"),
            tax_type=case.get("tax_type"),
            evidence_tiers=set(case["evidence_tiers"]) if case.get("evidence_tiers") else None,
            statuses=set(case["statuses"]) if case.get("statuses") else None,
        )
        ranked = bm25_rank(case["query"], docs, top_k=args.top_k)
        expected = set(case.get("expected_paths", []))
        rank = None
        for idx, (doc, _) in enumerate(ranked, 1):
            if doc.get("path") in expected:
                rank = idx
                break
        if rank:
            hits += 1
            reciprocal += 1 / rank
        details.append((case.get("id", ""), case["query"], rank, len(docs), [d.get("path") for d, _ in ranked]))

    total = len(cases)
    hit_rate = hits / total if total else 0.0
    mrr = reciprocal / total if total else 0.0
    lines = [
        "# 最近检索评测报告", "",
        f"- 日期：{date.today().isoformat()}",
        f"- 测试数：{total}",
        f"- Hit@{args.top_k}：{hit_rate:.1%}",
        f"- MRR：{mrr:.3f}",
        "- 说明：这是元数据过滤后的无模型 BM25 回归基线，用于发现分块、效力、地域或索引退化；不能代替专业税务评测。",
        "", "## 逐题结果", "",
    ]
    for case_id, query, rank, candidates, paths in details:
        lines.append(f"### {case_id} {query}")
        lines.append(f"- 过滤后候选：{candidates}")
        lines.append(f"- 命中排名：{rank if rank else '未命中'}")
        lines.append("- Top 路径：")
        lines.extend(f"  - `{p}`" for p in paths)
        lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Hit@{args.top_k}={hit_rate:.1%}, MRR={mrr:.3f} -> {report_path}")
    return 0 if total and hits == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
