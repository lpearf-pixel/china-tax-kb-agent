from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CLAUSE_RE = re.compile(r"^(第[〇零一二三四五六七八九十百千万两\d]+条(?:之[〇零一二三四五六七八九十百千万两\d]+)?)\s*(.*)$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_scalar(value: str) -> Any:
    value = _strip_quotes(value.strip())
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(x.strip()) for x in inner.split(",")]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the simple YAML subset used by this Vault without third-party deps."""
    match = FM_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    body = text[match.end():]
    meta: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        list_match = re.match(r"^\s+-\s+(.*)$", line)
        if list_match and current_key:
            if not isinstance(meta.get(current_key), list):
                meta[current_key] = []
            meta[current_key].append(_parse_scalar(list_match.group(1)))
            continue
        key_match = re.match(r"^([A-Za-z0-9_\-\u4e00-\u9fff]+):\s*(.*)$", line)
        if key_match:
            current_key = key_match.group(1)
            value = key_match.group(2)
            meta[current_key] = [] if value == "" else _parse_scalar(value)
    return meta, body


def extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    for raw in WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            links.append(target)
    return links


def resolve_wikilink(root: Path, target: str) -> Path | None:
    target = target.strip().replace("\\", "/")
    direct = root / target
    candidates = [direct] if direct.suffix == ".md" else [direct.with_suffix(".md"), direct]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    stem = Path(target).name
    matches = [p for p in root.rglob("*.md") if p.stem == stem]
    return matches[0].resolve() if len(matches) == 1 else None


def build_reverse_link_graph(root: Path) -> dict[str, list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for note in root.rglob("*.md"):
        if any(part.startswith(".") for part in note.relative_to(root).parts):
            continue
        text = note.read_text(encoding="utf-8", errors="replace")
        source_rel = note.relative_to(root).as_posix()
        for link in extract_wikilinks(text):
            resolved = resolve_wikilink(root, link)
            if resolved:
                target_rel = resolved.relative_to(root.resolve()).as_posix()
                graph[target_rel].add(source_rel)
    return {key: sorted(values) for key, values in graph.items()}


def _flush_chunk(chunks: list[dict[str, Any]], path: str, meta: dict[str, Any], heading: str, parts: list[str]) -> None:
    text = "\n".join(p.rstrip() for p in parts).strip()
    if not text:
        return
    chunk_id = hashlib.sha1(f"{path}|{heading}|{text}".encode("utf-8")).hexdigest()[:20]
    chunks.append({
        "chunk_id": chunk_id,
        "path": path,
        "heading": heading or meta.get("title", Path(path).stem),
        "text": text,
        "metadata": meta,
    })


def chunk_markdown(path: str, text: str, max_chars: int = 1600, overlap_chars: int = 160) -> list[dict[str, Any]]:
    meta, body = parse_frontmatter(text)
    chunks: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    current_heading = str(meta.get("title", Path(path).stem))
    parts: list[str] = []

    def flush() -> None:
        nonlocal parts
        _flush_chunk(chunks, path, meta, current_heading, parts)
        if overlap_chars and parts:
            tail = "\n".join(parts)[-overlap_chars:]
            parts = [tail] if tail.strip() else []
        else:
            parts = []

    for line in body.splitlines():
        hm = HEADING_RE.match(line)
        cm = CLAUSE_RE.match(line.strip())
        if hm:
            if parts:
                flush()
                parts = []
            level = len(hm.group(1))
            title = hm.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_heading = " / ".join(heading_stack)
            parts.append(line)
            continue
        if cm:
            if parts and len("\n".join(parts)) > max_chars // 3:
                flush()
                parts = []
            clause = cm.group(1)
            current_heading = " / ".join(heading_stack + [clause]) if heading_stack else clause
        parts.append(line)
        if len("\n".join(parts)) >= max_chars:
            flush()
    if parts:
        _flush_chunk(chunks, path, meta, current_heading, parts)
    return chunks


def tokenize(text: str) -> list[str]:
    text = text.lower()
    latin = re.findall(r"[a-z0-9_\-]+", text)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    tokens = list(latin)
    for run in chinese_runs:
        tokens.extend(run)
        if len(run) > 1:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def bm25_rank(query: str, docs: list[dict[str, Any]], top_k: int = 10, k1: float = 1.5, b: float = 0.75) -> list[tuple[dict[str, Any], float]]:
    if not docs:
        return []
    tokenized = [tokenize(str(doc.get("text", ""))) for doc in docs]
    q_tokens = tokenize(query)
    avg_len = sum(len(x) for x in tokenized) / max(len(tokenized), 1)
    doc_freq: Counter[str] = Counter()
    for toks in tokenized:
        doc_freq.update(set(toks))
    n = len(docs)
    scored: list[tuple[dict[str, Any], float]] = []
    for doc, toks in zip(docs, tokenized):
        freqs = Counter(toks)
        dl = len(toks)
        score = 0.0
        for term in q_tokens:
            if term not in freqs:
                continue
            df = doc_freq[term]
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = freqs[term]
            denom = tf + k1 * (1 - b + b * dl / max(avg_len, 1e-9))
            score += idf * (tf * (k1 + 1)) / denom
        scored.append((doc, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def iter_markdown(root: Path, excluded_prefixes: Iterable[str] = ()) -> Iterable[Path]:
    excluded = tuple(excluded_prefixes)
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in excluded):
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path


def select_note_for_profile(rel: str, profile: str) -> bool:
    rel = rel.replace("\\", "/")
    legal_prefixes = (
        "01-法规原文/",
        "02-条款结构/",
        "07-政策效力与关系/",
    )
    full_prefixes = legal_prefixes + (
        "03-概念解释/",
        "04-税种知识/",
        "05-纳税人类型/",
        "06-业务场景/",
        "08-税务规划案例/",
        "09-风险与争议/",
        "13-Workflow/",
        "14-Agent提示词/",
        "15-人工审签/",
    )
    if profile == "legal":
        return rel.startswith(legal_prefixes)
    if profile == "full":
        return rel.startswith(full_prefixes)
    raise ValueError(f"unknown profile: {profile}")


def _iso_date(value: Any):
    from datetime import date
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def filter_docs(
    docs: list[dict[str, Any]],
    jurisdiction: str | None = None,
    valid_on: str | None = None,
    tax_type: str | None = None,
    evidence_tiers: set[str] | None = None,
    statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Apply V5 hard metadata filters before retrieval.

    Local jurisdiction queries keep the national CN layer plus the requested
    regional overlay. By default, only currently usable material is retained;
    callers may explicitly request historical statuses. Provision-level dates
    and status override document-level metadata.
    """
    target_date = _iso_date(valid_on)
    allowed_statuses = statuses or {"effective", "partially_effective"}
    result: list[dict[str, Any]] = []
    for doc in docs:
        meta = doc.get("metadata") or {}
        scope = str(meta.get("jurisdiction_scope") or "").strip()
        if jurisdiction and scope not in {"", "CN", jurisdiction}:
            continue

        status = str(
            meta.get("provision_status")
            or meta.get("document_status")
            or meta.get("status")
            or "effective"
        ).strip()
        status_aliases = {"有效": "effective", "全文有效": "effective", "部分有效": "partially_effective", "已废止": "repealed", "失效": "expired", "待复核": "pending_review"}
        normalized_status = status_aliases.get(status, status)
        if normalized_status not in allowed_statuses:
            continue

        if evidence_tiers is not None:
            tier = str(meta.get("evidence_tier") or "").strip().upper()
            if tier not in {x.upper() for x in evidence_tiers}:
                continue

        if tax_type:
            raw_tax = meta.get("tax_types", meta.get("tax_type"))
            if isinstance(raw_tax, list):
                taxes = {str(x).lower() for x in raw_tax}
                if tax_type.lower() not in taxes:
                    continue
            elif raw_tax and tax_type.lower() not in str(raw_tax).lower():
                continue

        if target_date:
            effective = _iso_date(meta.get("provision_valid_from")) or _iso_date(meta.get("effective_date"))
            expiry = _iso_date(meta.get("provision_valid_to")) or _iso_date(meta.get("expiry_date"))
            if effective and target_date < effective:
                continue
            if expiry and target_date > expiry:
                continue
        result.append(doc)
    return result
