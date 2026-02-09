from flask import Flask
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/api/v1/health")
def health():
    return "True"

@app.route("/api/v1/modes")
def modes():
    with open("json/modos.json", "r") as f:
        return json.load(f)

@app.route("/api/v1/notes")
def notes():
    with open("json/notes.json", "r") as f:
        return json.load(f)

@app.route("/api/v1/scales/<string:note>/<string:mode>")
def scales(note, mode):
    with open("json/scales.json", "r") as f:
        scales_data = json.load(f)
        for item in scales_data:
            if note in item:
                return item[note][mode]
    return {"error": "Scale not found"}, 404