import pytest

from shop.stock import Stock


@pytest.fixture
def stock():
    return Stock()


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: slow test")
