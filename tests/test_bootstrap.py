from __future__ import annotations

from pathlib import Path

from pynterp import Interpreter


def test_nested_interpreter_bootstrap_style():
    kitchen_source = (Path(__file__).parent / "fixtures" / "kitchen_sink.py").read_text()
    direct_env = {}
    Interpreter(allowed_imports={"math"}).run(
        kitchen_source, env=direct_env, filename="<kitchen_sink_direct>"
    )

    bootstrap_source = """
inner = Interpreter(allowed_imports={"math"})
inner_env = {}
inner.run(KITCHEN_SOURCE, env=inner_env, filename="<kitchen_sink>")
BOOTSTRAP_RESULT = inner_env["RESULT"]
"""

    outer = Interpreter(allowed_imports={"math"})
    env = {
        "Interpreter": Interpreter,
        "KITCHEN_SOURCE": kitchen_source,
    }
    outer.run(bootstrap_source, env=env, filename="<bootstrap>")

    assert env["BOOTSTRAP_RESULT"] == direct_env["RESULT"]
