from __future__ import annotations

from collections import defaultdict
from pathlib import Path


class RelationGraph:
    def __init__(self) -> None:
        self.adjacency: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add(self, left: str, right: str, reason: str) -> None:
        if not left or not right or left == right:
            return
        self.adjacency[left][right].add(reason)
        self.adjacency[right][left].add(reason)

    @classmethod
    def build(cls, vault: Path | None, docs: list[dict]) -> "RelationGraph":
        graph = cls()
        by_document: dict[str, set[str]] = defaultdict(set)
        by_provision: dict[str, set[str]] = defaultdict(set)
        all_paths = {str(doc.get("path") or "") for doc in docs}
        for doc in docs:
            path = str(doc.get("path") or "")
            meta = doc.get("metadata") or {}
            if not path:
                continue
            if meta.get("document_id"):
                by_document[str(meta["document_id"])].add(path)
            if meta.get("provision_id"):
                by_provision[str(meta["provision_id"])].add(path)
        for paths in by_document.values():
            rows = sorted(paths)
            for index, left in enumerate(rows):
                for right in rows[index + 1 :]:
                    graph.add(left, right, "same_document_id")
        for paths in by_provision.values():
            rows = sorted(paths)
            for index, left in enumerate(rows):
                for right in rows[index + 1 :]:
                    graph.add(left, right, "same_provision_id")
        for doc in docs:
            path = str(doc.get("path") or "")
            meta = doc.get("metadata") or {}
            source_note = str(meta.get("source_note") or "")
            if source_note:
                target = source_note if source_note.endswith(".md") else source_note + ".md"
                if target in all_paths:
                    graph.add(path, target, "source_note")
            related = meta.get("related_provisions") or []
            if isinstance(related, str):
                related = [related]
            for provision_id in related:
                for target in by_provision.get(str(provision_id), set()):
                    graph.add(path, target, "related_provision")
        if vault and Path(vault).exists():
            try:
                import sys
                tools = Path(vault) / "90-工具"
                if str(tools) not in sys.path:
                    sys.path.insert(0, str(tools))
                from taxkb_core import extract_wikilinks, resolve_wikilink
                for path in all_paths:
                    note = Path(vault) / path
                    if not note.exists() or note.suffix != ".md":
                        continue
                    for link in extract_wikilinks(note.read_text(encoding="utf-8", errors="replace")):
                        resolved = resolve_wikilink(Path(vault), link)
                        if resolved:
                            target = resolved.relative_to(Path(vault).resolve()).as_posix()
                            graph.add(path, target, "wikilink")
            except (ImportError, OSError, ValueError):
                pass
        return graph

    def neighbors(self, path: str, max_hops: int = 1) -> list[tuple[str, list[str]]]:
        if max_hops != 1:
            raise ValueError("V7.1 supports exactly one relation hop")
        return [(neighbor, sorted(reasons)) for neighbor, reasons in sorted(self.adjacency.get(path, {}).items())]
