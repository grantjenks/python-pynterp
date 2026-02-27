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


def test_async_generator_frame_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def make_gen():
    yield 1

gen = make_gen()
frame = gen.ag_frame
RESULT = frame.f_globals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<async_frame_probe>")


def test_traceback_frame_globals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame
RESULT = frame.f_globals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<traceback_frame_probe>")


def test_object_getattribute_cannot_bypass_attr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = object.__getattribute__
RESULT = getter(f, "__globals__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<object_getattribute_probe>")
