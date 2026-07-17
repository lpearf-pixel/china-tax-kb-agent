#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from taxkb_core import chunk_markdown, iter_markdown, select_note_for_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Obsidian tax notes to clause-aware JSONL chunks.")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="90-工具/output/chunks.jsonl")
    parser.add_argument("--max-chars", type=int, default=1600)
    parser.add_argument("--profile", choices=["legal", "full"], default="full")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = vault / output
    output.parent.mkdir(parents=True, exist_ok=True)

    excluded = ("90-工具/", "99-归档/", "99-模板/", "10-法规更新记录/", "11-问题测试集/", "12-决策记录/", "docs/", ".obsidian/")
    count = 0
    with output.open("w", encoding="utf-8") as fh:
        for note in iter_markdown(vault, excluded):
            rel = note.relative_to(vault).as_posix()
            if not select_note_for_profile(rel, args.profile):
                continue
            for chunk in chunk_markdown(rel, note.read_text(encoding="utf-8", errors="replace"), args.max_chars):
                fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                count += 1
    print(f"exported {count} chunks -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
