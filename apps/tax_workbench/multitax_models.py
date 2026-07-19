from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import SchemeOption


class TaxAmount(str):
    """JSON-safe decimal text that still supports deterministic summation."""

    def __new__(cls, value):
        return super().__new__(cls, str(Decimal(str(value))))

    def __radd__(self, other):
        return Decimal(str(other)) + Decimal(str(self))

    def __add__(self, other):
        return Decimal(str(self)) + Decimal(str(other))


@dataclass(slots=True)
class MultiTaxSchemeOption(SchemeOption):
    tax_breakdown: dict[str, TaxAmount] = field(default_factory=dict)
