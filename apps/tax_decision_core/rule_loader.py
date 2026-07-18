from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Iterable

from .rule_schema import RuleDefinition

ID_RE = re.compile(r"^(document_id|provision_id):\s*[\"']?([^\"'\n]+?)[\"']?\s*$", re.MULTILINE)


class RuleLoader:
    def __init__(self, root: Path, *, vault: Path | None = None):
        self.root = Path(root).resolve()
        self.vault = Path(vault).resolve() if vault is not None else None
        self._legal_ids: set[str] | None = None

    def _index_legal_ids(self) -> set[str]:
        if self._legal_ids is not None:
            return self._legal_ids
        ids: set[str] = set()
        if self.vault and self.vault.exists():
            for note in self.vault.rglob("*.md"):
                text = note.read_text(encoding="utf-8", errors="replace")
                for _, value in ID_RE.findall(text):
                    ids.add(value.strip())
        self._legal_ids = ids
        return ids

    def _validate_legal_basis(self, rule: RuleDefinition) -> None:
        if self.vault is None:
            return
        ids = self._index_legal_ids()
        missing: list[str] = []
        for basis in rule.legal_basis:
            if basis.document_id not in ids:
                missing.append(basis.document_id)
            if basis.provision_id and basis.provision_id not in ids:
                missing.append(basis.provision_id)
        if missing:
            raise ValueError(f"rule {rule.rule_id} legal basis not found in Vault: {', '.join(sorted(set(missing)))}")

    @staticmethod
    def _parse_valid_on(valid_on: date | str) -> date:
        if isinstance(valid_on, date):
            return valid_on
        try:
            return date.fromisoformat(str(valid_on))
        except ValueError as exc:
            raise ValueError("valid_on must be YYYY-MM-DD") from exc

    def iter_rules(self) -> Iterable[RuleDefinition]:
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*.yaml")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"rule file must be JSON-compatible YAML: {path}: {exc}") from exc
            rule = RuleDefinition.from_mapping(raw)
            self._validate_legal_basis(rule)
            yield rule

    def load(self, valid_on: date | str, jurisdiction: str, tax_type: str) -> list[RuleDefinition]:
        target_date = self._parse_valid_on(valid_on)
        scopes = {"CN", jurisdiction}
        selected = [rule for rule in self.iter_rules() if rule.tax_type == tax_type and rule.jurisdiction in scopes and rule.is_effective_on(target_date)]
        selected.sort(key=lambda rule: (-rule.priority, rule.rule_id, -rule.version))
        return selected
