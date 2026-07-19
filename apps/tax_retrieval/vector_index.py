from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


_CANONICAL_PATTERNS = (
    (re.compile(r"百分之一|减按\s*1%|1\s*%\s*征收率"), "__rate_1pct__"),
    (re.compile(r"百分之三|3\s*%\s*征收率"), "__rate_3pct__"),
    (re.compile(r"零关税|免征进口关税"), "__zero_tariff__"),
    (re.compile(r"起征点|免税销售额"), "__threshold__"),
    (re.compile(r"专用发票|专票"), "__special_invoice__"),
    (re.compile(r"一般纳税人登记|超过\s*500\s*万"), "__general_registration__"),
)


def semantic_tokens(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9_%.-]+", normalized)
    for pattern, canonical in _CANONICAL_PATTERNS:
        if pattern.search(normalized):
            tokens.extend([canonical] * 4)
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.extend(run)
        tokens.extend(run[i : i + 2] for i in range(max(0, len(run) - 1)))
        tokens.extend(run[i : i + 3] for i in range(max(0, len(run) - 2)))
    return tokens


class HashingVectorizer:
    def __init__(self, dimensions: int = 512):
        if dimensions < 32:
            raise ValueError("dimensions must be >= 32")
        self.dimensions = dimensions

    def transform(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in semantic_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    @staticmethod
    def cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("vector dimensions differ")
        return sum(a * b for a, b in zip(left, right))


class HashingVectorIndex:
    def __init__(self, docs: list[dict], dimensions: int = 512):
        self.docs = docs
        self.vectorizer = HashingVectorizer(dimensions)
        self.vectors = [self.vectorizer.transform(self._doc_text(doc)) for doc in docs]

    @staticmethod
    def _doc_text(doc: dict) -> str:
        meta = doc.get("metadata") or {}
        return " ".join(str(value) for value in (meta.get("title"), meta.get("document_number"), meta.get("article_number"), doc.get("heading"), doc.get("text")) if value)

    def search(self, query: str, top_k: int = 10) -> list[tuple[dict, float]]:
        query_vector = self.vectorizer.transform(query)
        scored = [(doc, self.vectorizer.cosine(query_vector, vector)) for doc, vector in zip(self.docs, self.vectors)]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]
