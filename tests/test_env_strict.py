from __future__ import annotations

import pytest

from pynterp import Interpreter


def test_run_requires_explicit_env_dict():
    interpreter = Interpreter()
    with pytest.raises(TypeError):
        interpreter.run("RESULT = 1", env=None)  # type: ignore[arg-type]


def test_run_does_not_auto_insert_builtins_or_name():
    interpreter = Interpreter()
    env: dict = {}
    interpreter.run("RESULT = 1", env=env)
    assert env == {"RESULT": 1}


def test_empty_env_has_no_builtins():
    interpreter = Interpreter()
    with pytest.raises(NameError):
        interpreter.run("RESULT = len([1, 2, 3])", env={})


def test_make_default_env_provides_explicit_safe_defaults():
    interpreter = Interpreter(allowed_imports={"math"})
    env = interpreter.make_default_env()
    interpreter.run(
        "import math\nRESULT = (len(range(3)), round(math.sqrt(81)))",
        env=env,
    )
    assert env["RESULT"] == (3, 9)
