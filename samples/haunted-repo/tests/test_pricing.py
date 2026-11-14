from inventory.pricing import apply_discount, apply_seasonal_discount


def test_apply_discount():
    assert apply_discount(200, 10) == 180


def test_seasonal_discount():
    assert apply_seasonal_discount(100, "winter") == 90
