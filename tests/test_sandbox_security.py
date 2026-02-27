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


def test_type_getattribute_cannot_bypass_attr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = type.__getattribute__
RESULT = getter(f, "__globals__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<type_getattribute_probe>")


def test_super_getattribute_cannot_bypass_attr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Base:
    pass

class Child(Base):
    pass

child = Child()
getter = super(Child, child).__getattribute__
RESULT = getter("__dict__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<super_getattribute_probe>")


def test_user_function_interpreter_policy_mutation_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

probe.interpreter.allowed_imports = None
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<interpreter_policy_probe>")


def test_object_getattribute_cannot_reach_user_function_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = object.__getattribute__
RESULT = getter(probe, "interpreter")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<object_getattribute_interpreter_probe>")


def test_metaclass_getattribute_cannot_reach_subclasses_pivot():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

getter = Meta.__getattribute__
RESULT = getter(Probe, "__subclasses__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<metaclass_getattribute_probe>")


def test_function_closure_cell_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
RESULT = fn.__closure__[0].cell_contents
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<closure_cell_probe>")


def test_reduction_hook_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
RESULT = target.__reduce_ex__(4)
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<reduce_hook_probe>")


def test_object_getattribute_cannot_reach_reduction_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = object.__getattribute__
RESULT = getter(target, "__reduce_ex__")(4)
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<object_getattribute_reduce_hook_probe>")
