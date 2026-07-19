from __future__ import annotations

from .fact_graph import FactGraphService


class PitAwareFactGraphService(FactGraphService):
    @staticmethod
    def _affected_nodes(fact_id: str) -> tuple[str, ...]:
        if fact_id.startswith("pit."):
            return (
                "issues",
                "evidence",
                "rules",
                "calculation",
                "scenarios",
                "human_review",
            )
        return FactGraphService._affected_nodes(fact_id)
