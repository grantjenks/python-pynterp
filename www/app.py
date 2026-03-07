import contextlib
import io
import os

from flask import Flask, jsonify, render_template, request

from pynterp import Interpreter

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/run")
def run_code():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON body must be an object"}), 400

    code = payload.get("code", "")
    if not isinstance(code, str):
        return jsonify({"ok": False, "error": "code must be a string"}), 400

    interpreter = Interpreter(allowed_imports=set())
    env = interpreter.make_default_env(name="__main__")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = interpreter.run(code, env=env, filename="<user>")

    response = {
        "ok": result.ok,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "error": None if result.exception is None else str(result.exception),
        "exception_type": None if result.exception is None else type(result.exception).__name__,
    }
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
