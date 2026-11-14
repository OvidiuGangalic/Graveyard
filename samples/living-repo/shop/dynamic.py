import importlib
import json

try:
    import ujson as fastjson
except ImportError:
    fastjson = json

reports = importlib.import_module("shop.reports")


def run_report(kind):
    return getattr(reports, kind)()


def load(raw):
    return fastjson.loads(raw)
