from flask import Flask
from fastapi import FastAPI

flask_app = Flask(__name__)
api = FastAPI()


@flask_app.route("/health")
def health():
    return {"ok": True}


@api.get("/items/{item_id}")
def read_item(item_id: int):
    return {"id": item_id}
