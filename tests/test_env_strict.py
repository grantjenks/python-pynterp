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
    result = interpreter.run("RESULT = 1", env=env)
    assert result.ok
    assert env == {"RESULT": 1}


def test_empty_env_has_no_builtins():
    interpreter = Interpreter()
    result = interpreter.run("RESULT = len([1, 2, 3])", env={})
    assert isinstance(result.exception, NameError)


def test_make_default_env_provides_explicit_safe_defaults():
    interpreter = Interpreter(allowed_imports={"math"})
    env = interpreter.make_default_env()
    result = interpreter.run(
        "import math\nRESULT = (len(range(3)), round(math.sqrt(81)))",
        env=env,
    )
    assert result.ok
    assert env["RESULT"] == (3, 9)


def test_make_default_env_exposes_expanded_common_builtins():
    interpreter = Interpreter()
    env = interpreter.make_default_env()
    builtins_dict = env["__builtins__"]

    assert "AssertionError" in builtins_dict
    assert "DeprecationWarning" in builtins_dict
    assert "Ellipsis" in builtins_dict
    assert "NotImplemented" in builtins_dict
    assert "repr" in builtins_dict
    assert "sorted" in builtins_dict
    assert "chr" in builtins_dict
    assert "ord" in builtins_dict
    assert "pow" in builtins_dict
    assert "globals" in builtins_dict
    assert "locals" in builtins_dict
    assert "vars" in builtins_dict
    assert "dir" in builtins_dict
    assert "exit" in builtins_dict
    assert "quit" in builtins_dict
    assert "open" not in builtins_dict


def test_uncaught_system_exit_is_captured():
    interpreter = Interpreter()
    env = interpreter.make_default_env()

    result = interpreter.run("raise SystemExit(7)", env=env)
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 7


def test_builtins_exit_or_sys_exit_are_captured():
    interpreter = Interpreter()
    env = interpreter.make_default_env()

    result = interpreter.run(
        "import builtins\n"
        "import sys\n"
        "if hasattr(builtins, 'exit'):\n"
        "    builtins.exit(9)\n"
        "else:\n"
        "    sys.exit(9)\n",
        env=env,
    )
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 9


def test_uncaught_exception_is_captured_in_run_result():
    interpreter = Interpreter()
    env = interpreter.make_default_env()

    result = interpreter.run('raise Exception(\"foo\")', env=env)
    assert isinstance(result.exception, Exception)
    assert str(result.exception) == "foo"


def test_globals_locals_vars_dir_use_interpreter_scope():
    interpreter = Interpreter()
    env = interpreter.make_default_env()

    result = interpreter.run(
        "def snapshot():\n"
        "    x = 3\n"
        "    y = 4\n"
        "    return locals(), vars(), dir()\n"
        "\n"
        "globals_ns = globals()\n"
        "same_globals = globals_ns is globals()\n"
        "globals_ns['EXPOSED'] = 99\n"
        "locals_ns, vars_ns, dir_names = snapshot()\n"
        "RESULT = (same_globals, EXPOSED, locals_ns, vars_ns, dir_names)\n",
        env=env,
    )
    assert result.ok
    assert env["RESULT"] == (
        True,
        99,
        {"x": 3, "y": 4},
        {"x": 3, "y": 4},
        ["x", "y"],
    )


def test_vars_and_dir_with_object_argument_delegate_to_object_introspection():
    interpreter = Interpreter()
    env = interpreter.make_default_env()

    result = interpreter.run(
        "class Box:\n"
        "    def __init__(self):\n"
        "        self.value = 5\n"
        "\n"
        "def run():\n"
        "    box = Box()\n"
        "    return vars(box)['value'], ('value' in dir(box))\n"
        "\n"
        "RESULT = run()\n",
        env=env,
    )
    assert result.ok
    assert env["RESULT"] == (5, True)
