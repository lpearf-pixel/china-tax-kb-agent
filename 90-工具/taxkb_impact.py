#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
from datetime import date
from pathlib import Path
from taxkb_core import build_reverse_link_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Find rules/cases impacted by a changed law note.")
    parser.add_argument("changed", help="Changed note path relative to Vault")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--report", default="10-法规更新记录/更新影响报告/变更影响报告.md")
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    graph = build_reverse_link_graph(vault)
    start = args.changed.replace("\\", "/")
    if not start.endswith(".md"):
        start += ".md"

    seen = {start}
    queue = deque([(start, 0)])
    impacted: list[tuple[int, str]] = []
    while queue:
        node, depth = queue.popleft()
        for nxt in graph.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                impacted.append((depth + 1, nxt))
                queue.append((nxt, depth + 1))

    report = Path(args.report)
    if not report.is_absolute():
        report = vault / report
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 法规变更影响报告", "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 变更入口：`{start}`", f"- 受影响笔记：{len(impacted)}", "",
        "## 影响链", "",
    ]
    lines += [f"- L{depth} `{path}`" for depth, path in impacted] or ["- 未发现反向链接；请检查规则卡是否建立法源链接。"]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"impacted {len(impacted)} notes -> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
