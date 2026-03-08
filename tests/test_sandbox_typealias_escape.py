from __future__ import annotations

import ast
import builtins

import pytest

from pynterp import Interpreter

HAS_TYPE_ALIAS = hasattr(ast, "TypeAlias")


@pytest.mark.skipif(not HAS_TYPE_ALIAS, reason="TypeAlias requires Python 3.12+")
def test_typealias_does_not_reinject_host_builtins_after_builtins_delete(tmp_path):
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("sandbox escape\n")

    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env({"SECRET_PATH": str(secret_path)})
    assert "open" not in env["__builtins__"]

    source = """
del __builtins__
type Alias = int
RESULT = globals()["__builtins__"]["open"](SECRET_PATH).read()
"""

    with pytest.raises(KeyError):
        interp.run(source, env=env, filename="<typealias_builtins_escape>").raise_for_exception()

    assert "RESULT" not in env
    assert "__builtins__" not in env


def test_eval_builtin_does_not_reinject_host_builtins_after_builtins_delete():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    env["__builtins__"]["eval"] = builtins.eval

    interp.run(
        """
del __builtins__
RESULT = eval("'open' in __builtins__")
""",
        env=env,
        filename="<eval_builtins_restore_guard>",
    ).raise_for_exception()

    assert env["RESULT"] is False
    assert env["__builtins__"]["eval"] is builtins.eval
    assert "open" not in env["__builtins__"]


def test_exec_builtin_does_not_reinject_host_builtins_after_builtins_delete():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    env["__builtins__"]["exec"] = builtins.exec

    interp.run(
        """
del __builtins__
exec("RESULT = 'open' in __builtins__")
""",
        env=env,
        filename="<exec_builtins_restore_guard>",
    ).raise_for_exception()

    assert env["RESULT"] is False
    assert env["__builtins__"]["exec"] is builtins.exec
    assert "open" not in env["__builtins__"]
