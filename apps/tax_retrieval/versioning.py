from __future__ import annotations

from datetime import date
from typing import Any

from .models import RetrievalCandidate


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class VersionResolver:
    def resolve(self, candidates: list[RetrievalCandidate], valid_on: str | date, historical_requested: bool) -> list[RetrievalCandidate]:
        target = valid_on if isinstance(valid_on, date) else date.fromisoformat(str(valid_on))
        groups: dict[str, list[RetrievalCandidate]] = {}
        passthrough: list[RetrievalCandidate] = []
        for candidate in candidates:
            key = candidate.provision_id or candidate.document_id
            if not key:
                passthrough.append(candidate)
                continue
            groups.setdefault(key, []).append(candidate)
        selected = list(passthrough)
        for rows in groups.values():
            eligible: list[RetrievalCandidate] = []
            historical: list[RetrievalCandidate] = []
            for row in rows:
                meta = row.metadata
                status = str(meta.get("provision_status") or meta.get("document_status") or meta.get("status") or "effective")
                start = _parse_date(meta.get("provision_valid_from")) or _parse_date(meta.get("effective_date"))
                end = _parse_date(meta.get("provision_valid_to")) or _parse_date(meta.get("expiry_date"))
                valid = (start is None or start <= target) and (end is None or target <= end) and status not in {"repealed", "expired", "已废止", "失效"}
                if valid:
                    eligible.append(row)
                else:
                    historical.append(row)
            if eligible:
                eligible.sort(key=lambda row: (_parse_date(row.metadata.get("provision_valid_from")) or _parse_date(row.metadata.get("effective_date")) or date.min, row.rrf_score), reverse=True)
                selected.append(eligible[0])
            elif historical_requested and historical:
                historical.sort(key=lambda row: row.rrf_score, reverse=True)
                selected.append(historical[0])
        return selected
