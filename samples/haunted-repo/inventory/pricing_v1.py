def apply_discount(price, percent):
    """Original discount maths, kept around after the rewrite in pricing.py."""
    discounted = price - (price * percent / 100)
    return round(discounted, 2)
