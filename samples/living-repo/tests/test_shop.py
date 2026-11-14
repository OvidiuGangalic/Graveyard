import ast

from shop import banner, slugify
from shop.text import rank
from shop.visitor import NameCounter


def test_stock(stock):
    stock.adjust("A1", 3)
    assert stock.total == 3


def test_text():
    assert slugify("Big Box") == "big-box"
    assert rank([1, 2])[1] == 1.0


def test_visitor():
    counter = NameCounter()
    counter.visit(ast.parse("x = y"))
    assert counter.names == ["x", "y"]
    assert banner().startswith("shop")
