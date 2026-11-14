from typing import Optional


class Stock:
    """In-memory stock levels."""

    def __init__(self):
        self._levels = {}

    def __repr__(self):
        return f"Stock({len(self._levels)} skus)"

    def adjust(self, sku, delta):
        self._levels[sku] = self._levels.get(sku, 0) + delta
        return self._levels[sku]

    def rows(self):
        return [{"sku": sku, "quantity": qty} for sku, qty in sorted(self._levels.items())]

    def recount(self):
        """Clamp negative levels to zero. Written for the 2023 stocktake."""
        for sku in list(self._levels):
            self._levels[sku] = max(self._levels[sku], 0)
