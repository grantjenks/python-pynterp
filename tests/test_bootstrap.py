from __future__ import annotations

from pathlib import Path

from pynterp import Interpreter


def test_nested_interpreter_bootstrap_style():
    kitchen_path = Path(__file__).parent / "fixtures" / "kitchen_sink.py"
    kitchen_source = kitchen_path.read_text()
    direct_interpreter = Interpreter(allowed_imports={"math"})
    direct_env = direct_interpreter.make_default_env()
    direct_interpreter.run(kitchen_source, env=direct_env, filename="<kitchen_sink_direct>")

    bootstrap_source = """
from pathlib import Path
from pynterp.main import Interpreter as BootInterpreter

source = Path(KITCHEN_PATH).read_text()
inner = BootInterpreter(allowed_imports={"math"}, allow_relative_imports=True)
inner_env = inner.make_default_env()
inner.run(source, env=inner_env, filename="<kitchen_sink>")
BOOTSTRAP_RESULT = inner_env["RESULT"]
"""

    outer = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = outer.make_bootstrap_env(
        package_root=Path(__file__).resolve().parents[1] / "src" / "pynterp",
        env={
            "KITCHEN_PATH": str(kitchen_path),
        },
    )
    outer.run(bootstrap_source, env=env, filename="<bootstrap>")

    assert env["BOOTSTRAP_RESULT"] == direct_env["RESULT"]
