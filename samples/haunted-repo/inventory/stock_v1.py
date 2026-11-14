class StockV1:
    """First stock tracker: counts arrivals one unit at a time."""

    def __init__(self):
        self.counts = {}

    def adjust(self, sku):
        self.counts[sku] = self.counts.get(sku, 0) + 1
        return self.counts[sku]
