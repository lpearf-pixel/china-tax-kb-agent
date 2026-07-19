from __future__ import annotations

import re

from .models import RetrievalCandidate

_STATUS_ALIASES = {
    "有效": "effective",
    "全文有效": "effective",
    "部分有效": "partially_effective",
    "已废止": "repealed",
    "失效": "expired",
    "待复核": "pending_review",
}


class EvidenceClassifier:
    EXCLUSION_TERMS = ("不适用", "不得", "除外", "排除", "不包括", "不能直接", "全文废止", "被废止")
    LIMITATION_TERMS = ("应当", "必须", "仅限", "条件", "需要核验", "需核验", "同一计税期间", "全部应税交易", "前提")
    CONFLICT_TERMS = ("冲突", "不一致", "待复核", "效力争议", "uncertain")

    def classify(self, candidate: RetrievalCandidate, target_jurisdiction: str) -> tuple[str, list[str]]:
        meta = candidate.metadata
        status = str(meta.get("provision_status") or meta.get("document_status") or meta.get("status") or "effective")
        status = _STATUS_ALIASES.get(status, status)
        text = " ".join((candidate.heading, candidate.text, str(meta.get("title") or ""), candidate.path))
        reasons: list[str] = []
        if status in {"repealed", "expired"} or "99-归档/已废止" in candidate.path:
            return "historical", [f"status:{status}"]
        if status in {"uncertain", "pending_review"} or any(term in text for term in self.CONFLICT_TERMS):
            return "conflict", [f"status:{status}" if status in {"uncertain", "pending_review"} else "conflict_keyword"]
        exclusion_hits = [term for term in self.EXCLUSION_TERMS if term in text]
        if re.search(r"除.{0,50}(?:之外|以外)", text):
            exclusion_hits.append("除…之外")
        if exclusion_hits:
            return "exclusion", [f"keyword:{term}" for term in exclusion_hits[:3]]
        limitation_hits = [term for term in self.LIMITATION_TERMS if term in text]
        if limitation_hits:
            return "limitation", [f"keyword:{term}" for term in limitation_hits[:3]]
        scope = str(meta.get("jurisdiction_scope") or "CN")
        if target_jurisdiction != "CN" and scope == target_jurisdiction:
            return "local", [f"jurisdiction:{scope}"]
        if "local" in candidate.query_roles:
            reasons.append("query_role:local")
        return "support", reasons or ["default_support"]
