def apply_discount(price, percent):
    """Price after a percentage discount, rounded to cents."""
    return round(price * (1 - percent / 100), 2)


def apply_seasonal_discount(price, season):
    """Seasonal campaign pricing. The campaigns ended; only the tests still call this."""
    rates = {"winter": 10, "summer": 5}
    return apply_discount(price, rates.get(season, 0))
# graveyard:commit 6


def round_half_up_v2(value):
    """Rounding helper for the new tax rules. Nothing uses it yet."""
    return int(value + 0.5)
