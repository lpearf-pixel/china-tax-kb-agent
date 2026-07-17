#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from taxkb_core import parse_frontmatter

USER_AGENT = "TaxKB-Source-Watcher/1.0 (+local compliance knowledge base)"


def load_sources(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("national", []) + data.get("regions", []) + data.get("programs", [])


def discover_note_sources(vault: Path) -> list[dict]:
    """Discover exact official source URLs declared by regulation cards."""
    law_root = vault / "01-法规原文"
    if not law_root.exists():
        return []
    by_url: dict[str, dict] = {}
    for note in law_root.rglob("*.md"):
        if note.name.startswith("README") :
            continue
        meta, _ = parse_frontmatter(note.read_text(encoding="utf-8", errors="replace"))
        url = str(meta.get("source_url") or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        rel = note.relative_to(vault).as_posix()
        if url in by_url:
            by_url[url].setdefault("note_paths", []).append(rel)
            continue
        sid = "note_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        by_url[url] = {
            "id": sid,
            "name": str(meta.get("title") or note.stem),
            "jurisdiction": str(meta.get("jurisdiction_scope") or meta.get("jurisdiction") or "CN"),
            "level": str(meta.get("type") or "法规卡来源"),
            "url": url,
            "priority": 1,
            "watch_type": "exact_document",
            "note_path": rel,
            "note_paths": [rel],
        }
    return sorted(by_url.values(), key=lambda item: item["id"])


def fetch(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        body = resp.read()
        return {
            "final_url": resp.geturl(),
            "status_code": getattr(resp, "status", 200),
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "content_length": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch official tax source pages and create a change inbox report.")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--sources", default="90-工具/config/sources.json")
    parser.add_argument("--state", default="90-工具/state/source_state.json")
    parser.add_argument("--report-dir", default="10-法规更新记录/待审核")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--only", help="Comma-separated source IDs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-note-sources", action="store_true", help="Do not watch source_url values found in regulation cards")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    sources_path = vault / args.sources if not Path(args.sources).is_absolute() else Path(args.sources)
    state_path = vault / args.state if not Path(args.state).is_absolute() else Path(args.state)
    report_dir = vault / args.report_dir if not Path(args.report_dir).is_absolute() else Path(args.report_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    current = dict(previous)
    only = set(args.only.split(",")) if args.only else None
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    changes, errors = [], []

    sources = load_sources(sources_path)
    if not args.skip_note_sources:
        sources.extend(discover_note_sources(vault))
    deduped: dict[str, dict] = {}
    for source in sources:
        deduped.setdefault(source["id"], source)

    for source in deduped.values():
        sid = source["id"]
        if only and sid not in only:
            continue
        try:
            result = fetch(source["url"], args.timeout)
            old = previous.get(sid)
            changed = old is None or result["sha256"] != old.get("sha256") or result.get("etag") != old.get("etag")
            result.update({"checked_at": timestamp, "name": source["name"], "url": source["url"]})
            current[sid] = result
            if changed:
                changes.append((source, old, result))
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            errors.append((source, str(exc)))

    report_name = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S_来源变更检查.md")
    lines = [
        "# 官方来源变更检查", "", f"- 检查时间：{timestamp}",
        f"- 发生变化：{len(changes)}", f"- 请求失败：{len(errors)}", "",
        "> 页面变化只表示需要复核，不能自动认定法规已修改。确认后再更新法规卡、规则卡和案例卡。", "",
        "## 变化来源", "",
    ]
    for source, old, new in changes:
        kind = "首次建立基线" if old is None else "页面指纹变化"
        lines += [
            f"### {source['name']}", f"- ID：`{source['id']}`", f"- 类型：{source.get('level', '')}",
            f"- 地域：{source.get('jurisdiction', 'CN')}", f"- 变化：{kind}", f"- URL：{source['url']}",
            *([f"- 关联法规卡：`{source['note_path']}`"] if source.get("note_path") else []),
            f"- 新 SHA256：`{new['sha256']}`", "- 下一步：人工确认是否有新增、修改、废止或解读更新。", "",
        ]
    if not changes:
        lines.append("- 无")
    lines += ["", "## 请求失败", ""]
    lines += [f"- `{s['id']}` {s['name']}：{err}" for s, err in errors] or ["- 无"]
    (report_dir / report_name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not args.dry_run:
        state_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"changes={len(changes)} errors={len(errors)} report={report_dir / report_name}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
