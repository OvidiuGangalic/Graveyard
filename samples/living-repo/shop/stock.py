from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


class Stock:
    def __init__(self):
        self.levels = {}

    def __repr__(self):
        return f"Stock({self.levels})"

    @property
    def total(self):
        return sum(self.levels.values())

    def adjust(self, sku, delta=0):
        self.levels[sku] = self.levels.get(sku, 0) + delta

    def value(self, price: "Decimal"):
        return self.total * price


def factorial(n):
    return 1 if n <= 1 else n * factorial(n - 1)
