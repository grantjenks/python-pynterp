from __future__ import annotations

import pytest

from pynterp import Interpreter


def test_dunder_attribute_access_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        interp.run("RESULT = ().__class__.__mro__", env=env, filename="<dunder_block>")


def test_subclasses_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
subs = ().__class__.__mro__[1].__subclasses__()
RESULT = len(subs)
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<escape_probe>")


def test_generator_frame_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
RESULT = frame.f_globals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<frame_probe>")
