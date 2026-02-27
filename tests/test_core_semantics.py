from __future__ import annotations

from pathlib import Path

import pytest

EXPECTED_KITCHEN_RESULT = {
    "flag": "module",
    "sqrt": 9.0,
    "counter": [11, 13, 14],
    "box_scaled": 21,
    "trace": ["enter", "exit"],
    "with_total": 12,
    "pairs": [(0, 1), (0, 2), (2, 1), (2, 2)],
    "squares": {0: 0, 1: 1, 2: 4, 4: 16},
    "unique_mod": {0, 1, 2},
    "gen_values": [100, 101, 102, 103],
    "loop_total": 9,
    "del_error": "NameError",
    "exc_name": "ZeroDivisionError",
    "final_flag": "finally",
    "cascade": [0, 1, 2, "done"],
}


def test_kitchen_sink_fixture_runs(run_interpreter):
    source = (Path(__file__).parent / "fixtures" / "kitchen_sink.py").read_text()
    env = run_interpreter(source, allowed_imports={"math"}, filename="<kitchen_sink>")
    assert env["RESULT"] == EXPECTED_KITCHEN_RESULT


def test_nonlocal_closure(run_interpreter):
    source = """
def outer():
    value = 1
    def inner():
        nonlocal value
        value = value + 1
        return value
    return inner(), inner()

RESULT = outer()
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (2, 3)


def test_comprehension_target_does_not_leak(run_interpreter):
    source = """
x = 99
_ = [x for x in range(3)]
RESULT = x
"""
    env = run_interpreter(source)
    assert env["RESULT"] == 99


def test_import_restriction(run_interpreter):
    source = """
import os
"""
    with pytest.raises(ImportError):
        run_interpreter(source, allowed_imports={"math"})
