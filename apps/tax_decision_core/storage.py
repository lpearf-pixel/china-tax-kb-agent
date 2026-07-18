from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .domain import CaseRecord


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
KIND_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class CaseStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_case_id(case_id: str) -> str:
        if not CASE_ID_RE.fullmatch(case_id or ""):
            raise ValueError("invalid case_id")
        return case_id

    @staticmethod
    def _validate_kind(kind: str) -> str:
        if not KIND_RE.fullmatch(kind or ""):
            raise ValueError("invalid version kind")
        return kind

    def _case_dir(self, case_id: str) -> Path:
        return self.root / self._validate_case_id(case_id)

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def create(self, case: CaseRecord) -> Path:
        case_dir = self._case_dir(case.case_id)
        case_dir.mkdir(parents=False, exist_ok=False)
        path = case_dir / "case.json"
        try:
            self._atomic_json(path, case.to_dict())
        except Exception:
            case_dir.rmdir()
            raise
        return path

    def load(self, case_id: str) -> CaseRecord:
        path = self._case_dir(case_id) / "case.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return CaseRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def update_case(self, case: CaseRecord) -> Path:
        path = self._case_dir(case.case_id) / "case.json"
        if not path.exists():
            raise FileNotFoundError(path)
        self._atomic_json(path, case.to_dict(), overwrite=True)
        return path

    def write_version(self, case_id: str, kind: str, version: int, payload: dict[str, Any]) -> Path:
        if version < 1:
            raise ValueError("version must be >= 1")
        case_dir = self._case_dir(case_id)
        if not (case_dir / "case.json").exists():
            raise FileNotFoundError(case_dir / "case.json")
        safe_kind = self._validate_kind(kind)
        path = case_dir / f"{safe_kind}-v{version:03d}.json"
        self._atomic_json(path, payload)
        return path

    def append_event(self, case_id: str, event: dict[str, Any]) -> Path:
        case_dir = self._case_dir(case_id)
        if not (case_dir / "case.json").exists():
            raise FileNotFoundError(case_dir / "case.json")
        path = case_dir / "timeline.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path
