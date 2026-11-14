class Registry:
    """Collects webhook handlers by function name."""

    def __init__(self):
        self.hooks = {}

    def register(self, func):
        self.hooks[func.__name__] = func
        return func


registry = Registry()
