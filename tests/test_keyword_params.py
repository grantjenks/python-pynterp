from __future__ import annotations

import pytest


def test_kwonly_argument_is_bindable(run_interpreter):
    source = """
def f(*, x):
    return x

RESULT = f(x=7)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == 7


def test_kwonly_argument_with_kwargs_bucket(run_interpreter):
    source = """
def f(*, x, **kw):
    return x, kw

RESULT = f(x=1, y=2)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (1, {"y": 2})


@pytest.mark.parametrize(
    "call_expr",
    [
        "f(x=1, **{'x': 2})",
        "f(**{'x': 1}, **{'x': 2})",
    ],
)
def test_duplicate_keyword_via_unpack_raises(call_expr, run_interpreter):
    source = f"""
def f(x):
    return x

try:
    {call_expr}
except Exception as e:
    RESULT = type(e).__name__, str(e)
"""
    env = run_interpreter(source)
    assert env["RESULT"][0] == "TypeError"
    assert "multiple values for keyword argument 'x'" in env["RESULT"][1]
