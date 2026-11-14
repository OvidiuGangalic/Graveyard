def normalise(values):
    top = max(values)
    return [v / top for v in values]
