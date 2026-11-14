"""Shop package. Re-exports its public helpers."""
from shop.text import slugify
from shop.cli import main

__all__ = ["slugify", "main", "VERSION", "banner"]

VERSION = "2.0.0"


def banner():
    return f"shop {VERSION}"
