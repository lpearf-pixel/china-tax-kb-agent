#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from taxkb_core import bm25_rank, filter_docs


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"chunks not found: {path}; run taxkb_export.py first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def csv_set(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Search exported TaxKB chunks with hard date/region/tax/evidence filters.")
    parser.add_argument("query")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--chunks", default="90-工具/output/chunks.jsonl")
    parser.add_argument("--jurisdiction", help="CN-XJ or CN-HI; the national CN layer is retained")
    parser.add_argument("--valid-on", help="YYYY-MM-DD")
    parser.add_argument("--tax-type")
    parser.add_argument("--evidence-tier", help="comma-separated, e.g. A or A,B")
    parser.add_argument("--include-status", help="comma-separated; default effective,partially_effective")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    chunk_path = Path(args.chunks)
    if not chunk_path.is_absolute():
        chunk_path = vault / chunk_path
    docs = filter_docs(
        load_jsonl(chunk_path),
        jurisdiction=args.jurisdiction,
        valid_on=args.valid_on,
        tax_type=args.tax_type,
        evidence_tiers=csv_set(args.evidence_tier),
        statuses=csv_set(args.include_status),
    )
    ranked = bm25_rank(args.query, docs, top_k=args.top_k)
    rows = []
    for doc, score in ranked:
        rows.append({
            "score": round(score, 4),
            "path": doc.get("path"),
            "heading": doc.get("heading"),
            "text": str(doc.get("text", ""))[:500],
            "metadata": doc.get("metadata", {}),
        })
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"query={args.query!r} candidates={len(docs)} results={len(rows)}")
        for index, row in enumerate(rows, 1):
            print(f"\n[{index}] score={row['score']} {row['path']} :: {row['heading']}")
            print(row["text"].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
