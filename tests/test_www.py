from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_www_app():
    module = import_module("www.app")
    return module.app


def test_index_includes_issue_requested_www_controls():
    app = load_www_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="clear"' in html
    assert 'id="example"' in html
    assert "load an example and run it..." in html
    assert "feature: async and await" in html
    assert "blocked: import builtins" in html
