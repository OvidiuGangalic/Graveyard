ACTIONS = ["handle_refund"]


def handle_refund(order):
    return {"order": order, "status": "refunded"}


def dispatch(action, order):
    """Run an action by name. Actions are looked up at runtime, not called directly."""
    if action not in ACTIONS:
        raise ValueError(action)
    return globals()[action](order)
