import inventory.signals
from fastapi import FastAPI

from inventory.pricing import apply_discount
from inventory.registry import registry

app = FastAPI()


@app.get("/price/{sku}")
def get_price(sku: str, percent: float = 0):
    return {"sku": sku, "price": apply_discount(100.0, percent)}


@registry.register
def old_webhook(payload):
    """Webhook for the retired fulfilment partner."""
    return {"received": bool(payload)}
