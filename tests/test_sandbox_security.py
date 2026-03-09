from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from pynterp import Interpreter

HAS_HOST_ANNOTATE = hasattr(lambda: None, "__annotate__")


def run_raises(interp: Interpreter, source: str, *, env: dict, filename: str) -> None:
    interp.run(source, env=env, filename=filename).raise_for_exception()


def test_dunder_attribute_access_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(interp, "RESULT = ().__class__.__mro__", env=env, filename="<dunder_block>")


def test_subclasses_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
subs = ().__class__.__mro__[1].__subclasses__()
RESULT = len(subs)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<escape_probe>")


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
        run_raises(interp, source, env=env, filename="<frame_probe>")


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
        run_raises(interp, source, env=env, filename="<async_frame_probe>")


def test_type_getattribute_cannot_reach_coroutine_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = type.__getattribute__
    RESULT = getter(frame, "f_globals")
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_coroutine_frame_globals_probe>",
        )


def test_super_getattribute_cannot_reach_async_generator_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def produce():
    yield 1

ag = produce()
ag_getter = super(type(ag), ag).__getattribute__
frame = ag_getter("ag_frame")
frame_getter = super(type(frame), frame).__getattribute__
RESULT = frame_getter("f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_async_generator_frame_locals_probe>",
        )


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
        run_raises(interp, source, env=env, filename="<traceback_frame_probe>")


def test_type_getattribute_cannot_reach_traceback_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    tb = exc.__traceback__
    frame = tb.tb_frame
getter = type.__getattribute__
RESULT = getter(frame, "f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_traceback_frame_globals_probe>",
        )


def test_type_getattribute_tb_next_chain_cannot_reach_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    tb = exc.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    frame = tb.tb_frame
getter = type.__getattribute__
RESULT = getter(frame, "f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_tb_next_chain_frame_locals_probe>",
        )


def test_traceback_frame_builtins_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame
RESULT = frame.f_builtins["open"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<traceback_frame_builtins_probe>")


def test_traceback_tb_next_frame_locals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    tb = exc.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
RESULT = tb.tb_frame.f_locals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<traceback_tb_next_frame_locals_probe>")


def test_traceback_f_back_chain_globals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    frame = exc.__traceback__.tb_frame
    while frame.f_back is not None:
        frame = frame.f_back
RESULT = frame.f_globals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<traceback_f_back_frame_globals_probe>")


def test_object_getattribute_cannot_reach_traceback_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    tb = exc.__traceback__

getter = object.__getattribute__
RESULT = getter(tb.tb_frame, "f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_traceback_frame_globals_probe>",
        )


def test_object_getattribute_cannot_reach_traceback_frame_builtins():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    tb = exc.__traceback__

getter = object.__getattribute__
RESULT = getter(tb.tb_frame, "f_builtins")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_traceback_frame_builtins_probe>",
        )


def test_object_getattribute_tb_frame_back_chain_cannot_reach_frame_builtins():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    getter = object.__getattribute__
    tb = getter(exc, "__traceback__")
    frame = getter(tb, "tb_frame")
    while getter(frame, "f_back") is not None:
        frame = getter(frame, "f_back")

RESULT = getter(frame, "f_builtins")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_tb_frame_back_chain_frame_builtins_probe>",
        )


def test_type_getattribute_tb_frame_back_chain_cannot_reach_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    tb = exc.__traceback__

tb_getter = type(tb).__getattribute__
frame = tb_getter(tb, "tb_frame")
frame_getter = type(frame).__getattribute__
while frame_getter(frame, "f_back") is not None:
    frame = frame_getter(frame, "f_back")
RESULT = frame_getter(frame, "f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_tb_frame_back_chain_frame_locals_probe>",
        )


def test_exception_context_traceback_frame_globals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def trigger():
    try:
        1 / 0
    except Exception:
        raise RuntimeError("boom")

try:
    trigger()
except Exception as exc:
    tb = exc.__context__.__traceback__
RESULT = tb.tb_frame.f_globals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<exception_context_traceback_probe>")


def test_exception_cause_traceback_frame_locals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def trigger():
    try:
        1 / 0
    except Exception as root:
        raise RuntimeError("boom") from root

try:
    trigger()
except Exception as exc:
    tb = exc.__cause__.__traceback__
RESULT = tb.tb_frame.f_locals["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<exception_cause_traceback_probe>")


def test_object_getattribute_cannot_reach_exception_context_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def trigger():
    try:
        1 / 0
    except Exception:
        raise RuntimeError("boom")

try:
    trigger()
except Exception as exc:
    getter = object.__getattribute__
    context = getter(exc, "__context__")
    tb = getter(context, "__traceback__")
    frame = getter(tb, "tb_frame")
RESULT = frame.f_globals
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_exception_context_frame_probe>",
        )


def test_coroutine_frame_locals_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    RESULT = frame.f_locals["__builtins__"]
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<coroutine_frame_locals_probe>")


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
        run_raises(interp, source, env=env, filename="<object_getattribute_probe>")


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
        run_raises(interp, source, env=env, filename="<type_getattribute_probe>")


def test_function_globals_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

RESULT = f.__globals__["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<function_globals_probe>")


def test_super_getattribute_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = super(type(f), f).__getattribute__
RESULT = getter("__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_globals_probe>")


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
        run_raises(interp, source, env=env, filename="<super_getattribute_probe>")


def test_setattr_dunder_mutator_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
RESULT = target.__setattr__("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<setattr_dunder_probe>")


def test_object_getattribute_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = object.__getattribute__
RESULT = getter(target, "__setattr__")("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_setattr_probe>")


def test_type_getattribute_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = type.__getattribute__
RESULT = getter(target, "__setattr__")("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_setattr_probe>")


def test_super_getattribute_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = super(type(target), target).__getattribute__
RESULT = getter("__setattr__")("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_setattr_probe>")


def test_delattr_dunder_mutator_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
RESULT = target.__delattr__("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<delattr_dunder_probe>")


def test_object_getattribute_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = object.__getattribute__
RESULT = getter(target, "__delattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_delattr_probe>")


def test_type_getattribute_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = type.__getattribute__
RESULT = getter(target, "__delattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_delattr_probe>")


def test_super_getattribute_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = super(type(target), target).__getattribute__
RESULT = getter("__delattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_delattr_probe>")


def test_descriptor_rebound_bound_getattribute_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter("__setattr__")("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_setattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(name="__setattr__")("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_setattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_setattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
key = "name"
RESULT = getter(**{key: "__setattr__"})("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_setattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter("__delattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_delattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(name="__delattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_delattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_delattr_dunder_mutator():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = target.__getattribute__.__get__(None, type(target))
key = "name"
RESULT = getter(**{key: "__delattr__"})("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_delattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter("__getattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_dunder_getattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(name="__getattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_dunder_getattr_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
key = "name"
RESULT = getter(**{key: "__getattr__"})("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_dunder_getattr_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_setattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__setattr__")
RESULT = getter(name=name)("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_setattr_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_delattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

target = Probe()
target.marker = 1
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__delattr__")
RESULT = getter(name=name)("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_delattr_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_dunder_getattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__getattr__")
RESULT = getter(name=name)("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_dunder_getattr_probe>",
        )


def test_function_code_object_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

RESULT = f.__code__.co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<function_code_probe>")


def test_object_getattribute_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = object.__getattribute__
RESULT = getter(f, "__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_code_probe>")


def test_type_getattribute_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = type.__getattribute__
RESULT = getter(f, "__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_code_probe>")


def test_super_getattribute_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = super(type(f), f).__getattribute__
RESULT = getter("__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_code_probe>")


def test_bound_getattribute_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

getter = f.__getattribute__
RESULT = getter("__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<bound_getattribute_code_probe>")


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def f():
    return 1

getter = f.__getattribute__
name = Sneaky("__code__")
RESULT = getter(name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_code_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def f():
    return 1

getter = f.__getattribute__
name = Sneaky("__code__")
RESULT = getter(name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_bound_getattribute_code_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def f():
    return 1

getter = f.__getattribute__
name = Sneaky("__code__")
RESULT = getter(name=name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_code_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def f():
    return 1

getter = f.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_code_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def f():
    return 1

key = Sneaky("name")
RESULT = object.__getattribute__(f, **{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_code_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def f():
    return 1

key = Sneaky("name")
RESULT = type.__getattribute__(f, **{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_code_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def f():
    return 1

getter = super(type(f), f).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_code_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_object_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def f():
    return 1

key = Sneaky("name")
RESULT = object.__getattribute__(f, **{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_object_getattribute_code_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_type_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def f():
    return 1

key = Sneaky("name")
RESULT = type.__getattribute__(f, **{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_type_getattribute_code_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_super_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def f():
    return 1

getter = super(type(f), f).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_super_getattribute_code_probe>",
        )


def test_builtin_callable_self_module_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
builtins_mod = len.__self__
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<builtin_callable_self_probe>")


def test_object_getattribute_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
builtins_mod = getter(len, "__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_builtin_callable_self_probe>",
        )


def test_type_getattribute_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = type.__getattribute__
builtins_mod = getter(len, "__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_builtin_callable_self_probe>",
        )


def test_super_getattribute_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = super(type(len), len).__getattribute__
builtins_mod = getter("__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_builtin_callable_self_probe>",
        )


def test_object_getattribute_keyword_name_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
builtins_mod = object.__getattribute__(len, name="__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_keyword_builtin_callable_self_probe>",
        )


def test_type_getattribute_keyword_name_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__self__")
builtins_mod = type.__getattribute__(len, name=name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_keyword_builtin_callable_self_probe>",
        )


def test_super_getattribute_keyword_name_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = super(type(len), len).__getattribute__
builtins_mod = getter(name="__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_keyword_builtin_callable_self_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_super_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__self__")
getter = super(type(len), len).__getattribute__
builtins_mod = getter(name=name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_super_getattribute_builtin_callable_self_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "open"

name = Sneaky("__self__")
getter = super(type(len), len).__getattribute__
builtins_mod = getter(name=name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_builtin_callable_self_probe>",
        )


def test_bound_getattribute_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = len.__getattribute__
builtins_mod = getter("__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_builtin_callable_self_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = len.__getattribute__
name = Sneaky("__self__")
builtins_mod = getter(name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_builtin_callable_self_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_bound_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "open"

getter = len.__getattribute__
name = Sneaky("__self__")
builtins_mod = getter(name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_bound_getattribute_builtin_callable_self_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = len.__getattribute__
builtins_mod = getter(name="__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_builtin_callable_self_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = len.__getattribute__
name = Sneaky("__self__")
builtins_mod = getter(name=name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_builtin_callable_self_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "open"

getter = len.__getattribute__
name = Sneaky("__self__")
builtins_mod = getter(name=name)
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_builtin_callable_self_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_bound_getattribute_builtin_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = len.__getattribute__
key = Sneaky("name")
builtins_mod = getter(**{key: "__self__"})
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_bound_getattribute_builtin_callable_self_probe>",
        )


def test_import_callable_self_interpreter_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
host = __import__.__self__
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<import_callable_self_probe>")


def test_object_getattribute_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
host = getter(__import__, "__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_import_callable_self_probe>",
        )


def test_type_getattribute_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = type.__getattribute__
host = getter(__import__, "__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_import_callable_self_probe>",
        )


def test_super_getattribute_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = super(type(__import__), __import__).__getattribute__
host = getter("__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_import_callable_self_probe>",
        )


def test_object_getattribute_keyword_name_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
host = object.__getattribute__(__import__, name="__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_keyword_import_callable_self_probe>",
        )


def test_type_getattribute_keyword_name_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__self__")
host = type.__getattribute__(__import__, name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_keyword_import_callable_self_probe>",
        )


def test_super_getattribute_keyword_name_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(__import__), __import__).__getattribute__
name = Sneaky("__self__")
host = getter(name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_keyword_import_callable_self_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_getattr_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__self__")
RESULT = getattr(__import__, name).allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_getattr_import_callable_self_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_object_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = object.__getattribute__
name = Sneaky("__self__")
RESULT = getter(__import__, name).allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_object_getattribute_import_callable_self_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_super_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = super(type(__import__), __import__).__getattribute__
name = Sneaky("__self__")
RESULT = getter(name).allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_super_getattribute_import_callable_self_probe>",
        )


def test_bound_getattribute_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = __import__.__getattribute__
host = getter("__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_import_callable_self_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = __import__.__getattribute__
name = Sneaky("__self__")
host = getter(name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_import_callable_self_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_bound_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = __import__.__getattribute__
name = Sneaky("__self__")
host = getter(name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_bound_getattribute_import_callable_self_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = __import__.__getattribute__
host = getter(name="__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_import_callable_self_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = __import__.__getattribute__
name = Sneaky("__self__")
host = getter(name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_import_callable_self_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = __import__.__getattribute__
name = Sneaky("__self__")
host = getter(name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_import_callable_self_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_bound_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = __import__.__getattribute__
key = Sneaky("name")
host = getter(**{key: "__self__"})
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_bound_getattribute_import_callable_self_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_object_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = object.__getattribute__
name = Sneaky("__globals__")
RESULT = getter(probe, name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_object_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_type_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = type(probe).__getattribute__
name = Sneaky("__globals__")
RESULT = getter(probe, name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_type_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_super_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = super(type(probe), probe).__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_super_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

name = Sneaky("__globals__")
RESULT = object.__getattribute__(probe, name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

name = Sneaky("__globals__")
RESULT = type.__getattribute__(probe, name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

def probe():
    return 1

getter = super(type(probe), probe).__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_cannot_bypass_type_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = type(__import__).__getattribute__
name = Sneaky("__self__")
RESULT = getter(__import__, name).allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_type_getattribute_import_callable_self_probe>",
        )


def test_str_subclass_str_override_cannot_bypass_super_getattribute_import_callable_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(__import__), __import__).__getattribute__
name = Sneaky("__self__")
RESULT = getter(name).allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_super_getattribute_import_callable_self_probe>",
        )


def test_import_callable_func_globals_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
func = __import__.__func__
RESULT = func.__globals__["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<import_callable_func_globals_probe>")


def test_import_callable_func_cannot_be_rebound_with_forged_self(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{sandbox-escape}")
    source = f"""
f = __import__.__func__

class P:
    allow_relative_imports = False
    def _is_allowed_module(self, name): return True
    def _adapt_runtime_value(self, value): return value

b = f(P(), "builtins")
RESULT = b.open({str(flag_path)!r}).read()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<import_callable_func_forged_self_probe>")


def test_import_callable_func_descriptor_cannot_be_recovered_via_vars(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{sandbox-escape}")
    source = f"""
descriptor = vars(type(__import__))["__func__"]
f = descriptor.__get__(__import__, type(__import__))

class P:
    allow_relative_imports = False
    def _is_allowed_module(self, name): return True
    def _adapt_runtime_value(self, value): return value

b = f(P(), "builtins")
RESULT = b.open({str(flag_path)!r}).read()
"""
    with pytest.raises(KeyError):
        run_raises(interp, source, env=env, filename="<import_callable_func_vars_descriptor_probe>")


def test_object_getattribute_cannot_reach_import_callable_func_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
func = getter(__import__, "__func__")
RESULT = getter(func, "__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_import_callable_func_globals_probe>",
        )


def test_type_getattribute_cannot_reach_import_callable_func_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
method_getter = type(__import__).__getattribute__
func = method_getter(__import__, "__func__")
type_getter = type.__getattribute__
RESULT = type_getter(func, "__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_import_callable_func_globals_probe>",
        )


def test_super_getattribute_cannot_reach_import_callable_func_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
import_getter = super(type(__import__), __import__).__getattribute__
func = import_getter("__func__")
func_getter = super(type(func), func).__getattribute__
RESULT = func_getter("__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_import_callable_func_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_import_callable_func_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = object.__getattribute__
func = getter(__import__, "__func__")
key = Sneaky("name")
RESULT = getter(func, **{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_import_callable_func_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_import_callable_func_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

method_getter = type(__import__).__getattribute__
func = method_getter(__import__, "__func__")
key = Sneaky("name")
RESULT = type.__getattribute__(func, **{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_import_callable_func_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_import_callable_func_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

import_getter = super(type(__import__), __import__).__getattribute__
func = import_getter("__func__")
func_getter = super(type(func), func).__getattribute__
key = Sneaky("name")
RESULT = func_getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_import_callable_func_globals_probe>",
        )


def test_user_function_interpreter_policy_mutation_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

probe.interpreter.allowed_imports = None
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<interpreter_policy_probe>")


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
        run_raises(interp, source, env=env, filename="<object_getattribute_interpreter_probe>")


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
        run_raises(interp, source, env=env, filename="<metaclass_getattribute_probe>")


def test_str_subclass_str_override_positional_name_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_metaclass_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_metaclass_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_metaclass_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_metaclass_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_metaclass_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_metaclass_getattribute_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_metaclass_getattribute_class_subclasses_probe>",
        )


def test_metaclass_getattribute_cannot_reach_mro_pivot():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

getter = Meta.__getattribute__
RESULT = getter(Probe, "__mro__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<metaclass_getattribute_mro_probe>")


def test_str_subclass_str_override_positional_name_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__mro__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_metaclass_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__mro__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_metaclass_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__mro__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_metaclass_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__mro__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_metaclass_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_metaclass_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_metaclass_getattribute_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_metaclass_getattribute_class_mro_probe>",
        )


def test_metaclass_getattribute_cannot_reach_bases_pivot():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

getter = Meta.__getattribute__
RESULT = getter(Probe, "__bases__")[0]
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<metaclass_getattribute_bases_probe>")


def test_str_subclass_str_override_positional_name_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__bases__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_metaclass_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__bases__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_metaclass_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__bases__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_metaclass_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__bases__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_metaclass_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_metaclass_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_metaclass_getattribute_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_metaclass_getattribute_class_bases_probe>",
        )


def test_metaclass_getattribute_cannot_reach_base_pivot():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

getter = Meta.__getattribute__
RESULT = getter(Probe, "__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<metaclass_getattribute_base_probe>")


def test_str_subclass_str_override_positional_name_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__base__")
RESULT = getter(Probe, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_metaclass_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__base__")
RESULT = getter(Probe, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_metaclass_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = Meta.__getattribute__
name = Sneaky("__base__")
RESULT = getter(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_metaclass_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = Meta.__getattribute__
name = Sneaky("__base__")
RESULT = getter(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_metaclass_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_metaclass_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_metaclass_getattribute_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Meta(type):
    def __getattribute__(cls, name):
        return type.__getattribute__(cls, name)

class Probe(metaclass=Meta):
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = Meta.__getattribute__
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_metaclass_getattribute_class_base_probe>",
        )


def test_object_getattribute_cannot_reach_class_subclasses():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = object.__getattribute__
RESULT = getter(Probe, "__subclasses__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_class_subclasses_probe>",
        )


def test_type_getattribute_cannot_reach_class_subclasses():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__
RESULT = getter(Probe, "__subclasses__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_class_subclasses_probe>",
        )


def test_super_getattribute_cannot_reach_class_subclasses():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = super(type(Probe), Probe).__getattribute__
RESULT = getter("__subclasses__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__subclasses__")
RESULT = object.__getattribute__(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__subclasses__")
RESULT = type.__getattribute__(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(Probe), Probe).__getattribute__
name = Sneaky("__subclasses__")
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

key = Sneaky("name")
RESULT = object.__getattribute__(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

key = Sneaky("name")
RESULT = type.__getattribute__(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = super(type(Probe), Probe).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_class_subclasses_probe>",
        )


def test_class_base_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

RESULT = Probe.__base__
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<class_base_probe>")


def test_object_getattribute_cannot_reach_class_base():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = object.__getattribute__
RESULT = getter(Probe, "__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_class_base_probe>")


def test_type_getattribute_cannot_reach_class_base():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__
RESULT = getter(Probe, "__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_class_base_probe>")


def test_super_getattribute_cannot_reach_class_base():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = super(type(Probe), Probe).__getattribute__
RESULT = getter("__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_class_base_probe>")


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

key = Sneaky("name")
RESULT = object.__getattribute__(Probe, **{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

key = Sneaky("name")
RESULT = type.__getattribute__(Probe, **{key: "__bases__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = super(type(Probe), Probe).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_class_base_probe>",
        )


def test_class_bases_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

RESULT = Probe.__bases__
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<class_bases_probe>")


def test_object_getattribute_cannot_reach_class_bases():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = object.__getattribute__
RESULT = getter(Probe, "__bases__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_class_bases_probe>")


def test_type_getattribute_cannot_reach_class_bases():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__
RESULT = getter(Probe, "__bases__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_class_bases_probe>")


def test_super_getattribute_cannot_reach_class_bases():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = super(type(Probe), Probe).__getattribute__
RESULT = getter("__bases__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_class_bases_probe>")


def test_object_getattribute_cannot_reach_class_mro():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = object.__getattribute__
RESULT = getter(Probe, "__mro__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_class_mro_probe>")


def test_type_getattribute_cannot_reach_class_mro():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__
RESULT = getter(Probe, "__mro__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_class_mro_probe>")


def test_super_getattribute_cannot_reach_class_mro():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = super(type(Probe), Probe).__getattribute__
RESULT = getter("__mro__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_class_mro_probe>")


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__mro__")
RESULT = object.__getattribute__(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__mro__")
RESULT = type.__getattribute__(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(Probe), Probe).__getattribute__
name = Sneaky("__mro__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

key = Sneaky("name")
RESULT = object.__getattribute__(Probe, **{key: "__mro__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_name"

key = Sneaky("name")
RESULT = type.__getattribute__(Probe, **{key: "__mro__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = super(type(Probe), Probe).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__mro__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_class_mro_probe>",
        )


def test_dunder_getattr_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
RESULT = target.__getattr__("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<dunder_getattr_probe>")


def test_object_getattribute_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = object.__getattribute__
RESULT = getter(target, "__getattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_dunder_getattr_probe>")


def test_type_getattribute_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = type.__getattribute__
RESULT = getter(target, "__getattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_dunder_getattr_probe>")


def test_super_getattribute_cannot_reach_dunder_getattr():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = super(type(target), target).__getattribute__
RESULT = getter("__getattr__")("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_dunder_getattr_probe>")


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_dunder_getattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = Probe()
name = Sneaky("__getattr__")
RESULT = object.__getattribute__(target, name=name)("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_dunder_getattr_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_dunder_getattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = Probe()
name = Sneaky("__getattr__")
RESULT = type.__getattribute__(target, name=name)("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_dunder_getattr_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_dunder_getattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    def __getattr__(self, name):
        return name

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

target = Probe()
getter = super(type(target), target).__getattribute__
name = Sneaky("__getattr__")
RESULT = getter(name=name)("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_dunder_getattr_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_dunder_dict():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
target.marker = 1
getter = target.__getattribute__
RESULT = getter(name="__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp, source, env=env, filename="<bound_getattribute_keyword_dunder_dict_probe>"
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_dunder_dict_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = Probe()
name = Sneaky("__dict__")
getter = target.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_dunder_dict_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_super_getattribute_dunder_dict_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = Probe()
name = Sneaky("__dict__")
getter = super(type(target), target).__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_super_getattribute_dunder_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_dunder_dict_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

target = Probe()
name = Sneaky("__dict__")
getter = super(type(target), target).__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_dunder_dict_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_traceback_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__
RESULT = getter(name="f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_traceback_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_globals")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_builtins")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_traceback_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__
RESULT = getter(name="f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_traceback_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_locals")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_locals")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_coroutine_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__
    RESULT = getter(name="f_globals")
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_coroutine_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    name = Sneaky("f_builtins")
    getter = frame.__getattribute__
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    name = Sneaky("f_locals")
    getter = frame.__getattribute__
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_async_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__
RESULT = getter(name="f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_async_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
name = Sneaky("f_builtins")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
name = Sneaky("f_locals")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_async_generator_frame_locals_probe>",
        )


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
        run_raises(interp, source, env=env, filename="<closure_cell_probe>")


def test_object_getattribute_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = object.__getattribute__
cells = getter(fn, "__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_closure_cell_probe>",
        )


def test_type_getattribute_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = type.__getattribute__
cells = getter(fn, "__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_closure_cell_probe>",
        )


def test_super_getattribute_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = super(type(fn), fn).__getattribute__
cells = getter("__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_closure_cell_probe>",
        )


def test_bound_getattribute_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__
cells = getter("__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_closure_cell_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__
name = Sneaky("__closure__")
cells = getter(name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_closure_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__
name = Sneaky("__closure__")
cells = getter(name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_bound_getattribute_closure_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__
name = Sneaky("__closure__")
cells = getter(name=name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_closure_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__
key = Sneaky("name")
cells = getter(**{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_closure_probe>",
        )


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
        run_raises(interp, source, env=env, filename="<reduce_hook_probe>")


def test_reduce_hook_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
RESULT = target.__reduce__()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<reduce_probe>")


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
        run_raises(interp, source, env=env, filename="<object_getattribute_reduce_hook_probe>")


def test_object_getattribute_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = object.__getattribute__
RESULT = getter(target, "__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_reduce_probe>")


def test_type_getattribute_cannot_reach_reduction_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = type.__getattribute__
RESULT = getter(target, "__reduce_ex__")(4)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_reduce_hook_probe>")


def test_type_getattribute_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = type.__getattribute__
RESULT = getter(target, "__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_reduce_probe>")


def test_super_getattribute_cannot_reach_reduction_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = super(type(target), target).__getattribute__
RESULT = getter("__reduce_ex__")(4)
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_reduce_hook_probe>")


def test_super_getattribute_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = super(type(target), target).__getattribute__
RESULT = getter("__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_reduce_probe>")


def test_bound_getattribute_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

target = Probe()
getter = target.__getattribute__
RESULT = getter("__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<bound_getattribute_reduce_probe>")


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

target = Probe()
name = Sneaky("__reduce_ex__")
getter = target.__getattribute__
RESULT = getter(name)(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_reduce_hook_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

target = Probe()
name = Sneaky("__reduce__")
getter = target.__getattribute__
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_reduce_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

target = Probe()
getter = target.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__reduce_ex__"})(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_reduce_hook_probe>",
        )


def test_object_getattribute_cannot_reach_coroutine_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    getter = object.__getattribute__
    frame = getter(co, "cr_frame")
    RESULT = getter(frame, "f_globals")
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_coroutine_frame_globals_probe>",
        )


def test_object_getattribute_cannot_reach_coroutine_frame_builtins():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    getter = object.__getattribute__
    frame = getter(co, "cr_frame")
    RESULT = getter(frame, "f_builtins")
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_coroutine_frame_builtins_probe>",
        )


def test_object_getattribute_cannot_reach_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
getter = object.__getattribute__
frame = getter(gen, "gi_frame")
RESULT = getter(frame, "f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_generator_frame_globals_probe>",
        )


def test_type_getattribute_cannot_reach_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
getter = type.__getattribute__
frame = getter(gen, "gi_frame")
RESULT = getter(frame, "f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<type_getattribute_generator_frame_globals_probe>",
        )


def test_super_getattribute_cannot_reach_generator_frame_builtins():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
gen_getter = super(type(gen), gen).__getattribute__
frame = gen_getter("gi_frame")
frame_getter = super(type(frame), frame).__getattribute__
RESULT = frame_getter("f_builtins")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<super_getattribute_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_type_getattribute_generator_frame_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

gen = make_gen()
name = Sneaky("gi_frame")
RESULT = type.__getattribute__(gen, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_type_getattribute_generator_frame_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_generator_frame():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
getter = gen.__getattribute__
RESULT = getter(name="gi_frame")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_generator_frame_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_generator_frame_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def make_gen():
    yield 1

gen = make_gen()
name = Sneaky("gi_frame")
RESULT = object.__getattribute__(gen, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_generator_frame_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_generator_frame_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

def make_gen():
    yield 1

gen = make_gen()
getter = super(type(gen), gen).__getattribute__
name = Sneaky("gi_frame")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_generator_frame_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__
RESULT = getter(name="f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
name = Sneaky("f_builtins")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_blocked"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
name = Sneaky("f_locals")
getter = frame.__getattribute__
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_generator_frame_locals_probe>",
        )


def test_object_getattribute_cannot_reach_async_generator_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def produce():
    yield 1

ag = produce()
getter = object.__getattribute__
frame = getter(ag, "ag_frame")
RESULT = getter(frame, "f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_async_generator_frame_locals_probe>",
        )


def test_object_getattribute_tb_next_chain_cannot_reach_frame_locals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def boom():
    1 / 0

def run():
    boom()

try:
    run()
except Exception as exc:
    getter = object.__getattribute__
    tb = getter(exc, "__traceback__")
    while getter(tb, "tb_next") is not None:
        tb = getter(tb, "tb_next")
    frame = getter(tb, "tb_frame")

RESULT = getter(frame, "f_locals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<object_getattribute_tb_next_chain_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_globals")
RESULT = object.__getattribute__(frame, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_traceback_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

name = Sneaky("f_builtins")
RESULT = type.__getattribute__(frame, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_traceback_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

co = compute()
try:
    frame = co.cr_frame
    getter = super(type(frame), frame).__getattribute__
    name = Sneaky("f_locals")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_coroutine_frame_locals_probe>",
        )


def test_module_loader_import_smuggling_chain_is_blocked():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
loader = math.__loader__
RESULT = loader.load_module("os")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<module_loader_import_smuggling_probe>")


def test_module_spec_import_smuggling_chain_is_blocked():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
spec = math.__spec__
RESULT = spec.loader.load_module("os")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<module_spec_import_smuggling_probe>")


def test_module_dict_import_smuggling_chain_is_blocked():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
module_dict = math.__dict__
RESULT = module_dict["__loader__"].load_module("os")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<module_dict_import_smuggling_probe>")


def test_object_getattribute_cannot_reach_module_loader_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = object.__getattribute__
RESULT = getter(math, "__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_module_loader_probe>")


def test_object_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = object.__getattribute__
RESULT = getter(math, "__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<object_getattribute_module_dict_probe>")


def test_super_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = super(type(math), math).__getattribute__
RESULT = getter("__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_module_dict_probe>")


def test_type_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = type.__getattribute__
RESULT = getter(math, "__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_module_dict_probe>")


def test_type_getattribute_cannot_reach_module_spec_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = type.__getattribute__
RESULT = getter(math, "__spec__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<type_getattribute_module_spec_probe>")


def test_super_getattribute_cannot_reach_module_loader_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = super(type(math), math).__getattribute__
RESULT = getter("__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(interp, source, env=env, filename="<super_getattribute_module_loader_probe>")


def test_bound_getattribute_keyword_name_cannot_reach_module_loader_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = math.__getattribute__
RESULT = getter(name="__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_module_loader_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = math.__getattribute__
RESULT = getter(name="__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_module_dict_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_module_spec_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = math.__getattribute__
RESULT = getter(name="__spec__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = math.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_bound_getattribute_module_loader_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = math.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = super(type(math), math).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__spec__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = math.__getattribute__
name = Sneaky("__loader__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = math.__getattribute__
name = Sneaky("__dict__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_cannot_bypass_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = math.__getattribute__
name = Sneaky("__spec__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = math.__getattribute__
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = math.__getattribute__
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = math.__getattribute__
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = math.__getattribute__
name = Sneaky("__spec__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = math.__getattribute__
name = Sneaky("__spec__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = math.__getattribute__
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_getattr_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__loader__")
RESULT = getattr(math, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_getattr_module_loader_probe>",
        )


def test_stateful_str_subclass_cannot_bypass_type_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__spec__")
RESULT = type.__getattribute__(math, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_type_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_cannot_bypass_super_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(math), math).__getattribute__
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_super_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__loader__")
RESULT = object.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_super_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = super(type(math), math).__getattribute__
name = Sneaky("__spec__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_super_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_type_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

name = Sneaky("__loader__")
RESULT = type.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_type_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_type_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__dict__")
RESULT = type.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_object_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

name = Sneaky("__dict__")
RESULT = object.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_object_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_super_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = super(type(math), math).__getattribute__
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_super_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_type_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

name = Sneaky("__dict__")
RESULT = type.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_type_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_object_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

name = Sneaky("__dict__")
RESULT = object.__getattribute__(math, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_object_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_super_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_blocked"

getter = super(type(math), math).__getattribute__
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

co = compute()
try:
    frame = co.cr_frame
    getter = super(type(frame), frame).__getattribute__
    key = Sneaky("name")
    RESULT = getter(**{key: "f_builtins"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_coroutine_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

key = Sneaky("name")
RESULT = object.__getattribute__(frame, **{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_traceback_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
key = Sneaky("name")
RESULT = type.__getattribute__(frame, **{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_type_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

key = Sneaky("name")
RESULT = type.__getattribute__(math, **{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_type_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

key = Sneaky("name")
RESULT = object.__getattribute__(__import__, **{key: "__self__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_importer_self_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

key = Sneaky("name")
RESULT = type.__getattribute__(probe, **{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

key = Sneaky("name")
RESULT = object.__getattribute__(probe, **{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_type_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

key = Sneaky("name")
RESULT = type.__getattribute__(probe, **{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_type_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = super(type(probe), probe).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = super(type(len), len).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__self__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_builtin_self_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

target = Probe()
key = Sneaky("name")
RESULT = object.__getattribute__(target, **{key: "__reduce__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_reduce_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_type_getattribute_reduction_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

target = Probe()
key = Sneaky("name")
RESULT = type.__getattribute__(target, **{key: "__reduce_ex__"})(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_type_getattribute_reduction_hook_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_super_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

target = Probe()
getter = super(type(target), target).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__reduce__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_super_getattribute_reduce_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def outer():
    secret = 42
    def inner():
        return secret
    return inner

fn = outer()
key = Sneaky("name")
cells = object.__getattribute__(fn, **{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_closure_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def outer():
    secret = 42
    def inner():
        return secret
    return inner

fn = outer()
key = Sneaky("name")
cells = type.__getattribute__(fn, **{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_closure_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def outer():
    secret = 42
    def inner():
        return secret
    return inner

fn = outer()
getter = super(type(fn), fn).__getattribute__
key = Sneaky("name")
cells = getter(**{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_closure_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_object_getattribute_setattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

target = Probe()
key = Sneaky("name")
RESULT = object.__getattribute__(target, **{key: "__setattr__"})("marker", 1)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_object_getattribute_setattr_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_type_getattribute_delattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

target = Probe()
target.marker = 1
key = Sneaky("name")
RESULT = type.__getattribute__(target, **{key: "__delattr__"})("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_type_getattribute_delattr_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_super_getattribute_dunder_getattr_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    def __getattr__(self, name):
        return name

target = Probe()
getter = super(type(target), target).__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__getattr__"})("marker")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_super_getattribute_dunder_getattr_probe>",
        )


def test_bound_getattribute_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__
RESULT = getter("__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = probe.__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_bound_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

getter = probe.__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = probe.__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_bound_getattribute_function_globals_probe>",
        )


def test_bound_getattribute_keyword_name_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__
RESULT = getter(name="__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<bound_getattribute_keyword_function_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

getter = probe.__getattribute__
name = Sneaky("__globals__")
RESULT = getter(name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_bound_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

getter = probe.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = probe.__getattribute__
key = Sneaky("name")
RESULT = getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_bound_getattribute_function_globals_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter("__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter("__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter(name="__code__").co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_function_code_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_function_code_object():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter(**{"name": "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_function_code_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
key = Sneaky("name")
RESULT = getter(**{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__code__")
RESULT = getter(name=name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
key = Sneaky("name")
RESULT = getter(**{key: "__code__"}).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_code"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__code__")
RESULT = getter(name=name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__code__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__code__")
RESULT = getter(name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_code_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_code"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__code__")
RESULT = getter(name).co_consts
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_function_code_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
cells = getter("__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
cells = getter(name="__closure__")
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_function_closure_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_function_closure_cells():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
cells = getter(**{"name": "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_function_closure_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
key = Sneaky("name")
cells = getter(**{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
name = Sneaky("__closure__")
cells = getter(name=name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
key = Sneaky("name")
cells = getter(**{key: "__closure__"})
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_closure"

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
name = Sneaky("__closure__")
cells = getter(name=name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__closure__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
name = Sneaky("__closure__")
cells = getter(name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_closure_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_closure"

def outer():
    sentinel = 42

    def inner():
        return sentinel

    return inner

fn = outer()
getter = fn.__getattribute__.__get__(None, type(fn))
name = Sneaky("__closure__")
cells = getter(name)
RESULT = cells[0].cell_contents
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_function_closure_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter("__reduce_ex__")(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_reduce():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter("__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(name="__reduce__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_hook_keyword_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_reduce_ex_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(name="__reduce_ex__")(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_ex_keyword_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_reduce_hook():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(**{"name": "__reduce_ex__"})(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_hook_keyword_key_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_reduce():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
RESULT = getter(**{"name": "__reduce__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_reduce_keyword_key_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
key = Sneaky("name")
RESULT = getter(**{key: "__reduce__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_ex_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
key = Sneaky("name")
RESULT = getter(**{key: "__reduce_ex__"})(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_reduce_ex_hook_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
key = Sneaky("name")
RESULT = getter(**{key: "__reduce_ex__"})(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
key = Sneaky("name")
RESULT = getter(**{key: "__reduce__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_reduce_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce_ex__")
RESULT = getter(name=name)(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce__")
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_reduce_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_reduce"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce__")
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_ex_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_reduce_ex"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce_ex__")
RESULT = getter(name=name)(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_reduce_ex_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__reduce__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce__")
RESULT = getter(name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_ex_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__reduce_ex__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce_ex__")
RESULT = getter(name)(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_reduce_ex_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_hook_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_reduce"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce_ex__")
RESULT = getter(name)(4)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_reduce_hook_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_reduce_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_reduce"

target = [1, 2, 3]
getter = target.__getattribute__.__get__(None, type(target))
name = Sneaky("__reduce__")
RESULT = getter(name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_reduce_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_importer_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = __import__.__getattribute__.__get__(None, type(__import__))
host = getter("__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_importer_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = __import__.__getattribute__.__get__(None, type(__import__))
host = getter(name="__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_importer_self_keyword_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_importer_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = __import__.__getattribute__.__get__(None, type(__import__))
host = getter(**{"name": "__self__"})
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_importer_self_keyword_key_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_module_loader():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = math.__getattribute__.__get__(None, type(math))
RESULT = getter("__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_module_loader_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_module_spec():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = math.__getattribute__.__get__(None, type(math))
RESULT = getter("__spec__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_module_spec_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = math.__getattribute__.__get__(None, type(math))
RESULT = getter("__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter(name="__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_function_globals_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_function_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
RESULT = getter(**{"name": "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_keyword_key_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__globals__")
RESULT = getter(name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
key = Sneaky("name")
RESULT = getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__globals__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__globals__")
RESULT = getter(name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__globals__")
RESULT = getter(name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
key = Sneaky("name")
RESULT = getter(**{key: "__globals__"})["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_function_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

def probe():
    return 1

getter = probe.__getattribute__.__get__(None, type(probe))
name = Sneaky("__globals__")
RESULT = getter(name=name)["__builtins__"]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_function_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = __import__.__getattribute__.__get__(None, type(__import__))
key = Sneaky("name")
host = getter(**{key: "__self__"})
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = __import__.__getattribute__.__get__(None, type(__import__))
name = Sneaky("__self__")
host = getter(name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_self"

getter = __import__.__getattribute__.__get__(None, type(__import__))
name = Sneaky("__self__")
host = getter(name=name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = __import__.__getattribute__.__get__(None, type(__import__))
name = Sneaky("__self__")
host = getter(name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_self"

getter = __import__.__getattribute__.__get__(None, type(__import__))
name = Sneaky("__self__")
host = getter(name)
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_importer_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = __import__.__getattribute__.__get__(None, type(__import__))
key = Sneaky("name")
host = getter(**{key: "__self__"})
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_importer_self_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_loader"

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__loader__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_module_loader_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_builtin_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = len.__getattribute__.__get__(None, type(len))
RESULT = getter("__self__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_name_cannot_reach_builtin_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = len.__getattribute__.__get__(None, type(len))
RESULT = getter(name="__self__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_builtin_self_keyword_probe>",
        )


def test_descriptor_rebound_bound_getattribute_keyword_key_cannot_reach_builtin_self():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = len.__getattribute__.__get__(None, type(len))
RESULT = getter(**{"name": "__self__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_builtin_self_keyword_key_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = len.__getattribute__.__get__(None, type(len))
key = Sneaky("name")
RESULT = getter(**{key: "__self__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = len.__getattribute__.__get__(None, type(len))
name = Sneaky("__self__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_self"

getter = len.__getattribute__.__get__(None, type(len))
name = Sneaky("__self__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = len.__getattribute__.__get__(None, type(len))
name = Sneaky("__self__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_self"

getter = len.__getattribute__.__get__(None, type(len))
name = Sneaky("__self__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_builtin_self_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = len.__getattribute__.__get__(None, type(len))
key = Sneaky("name")
RESULT = getter(**{key: "__self__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_builtin_self_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__spec__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

import math

getter = math.__getattribute__.__get__(None, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__spec__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

import math

getter = math.__getattribute__.__get__(None, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__dict__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__dict__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__dict__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_dict"

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__dict__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_dict"

import math

getter = math.__getattribute__.__get__(None, type(math))
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

import math

getter = math.__getattribute__.__get__(None, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

import math

getter = math.__getattribute__.__get__(None, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_module_dict_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_traceback_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
RESULT = getter("f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_coroutine_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    RESULT = getter("f_globals")
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_globals")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_locals")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_builtins")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_builtins"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_async_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
RESULT = getter("f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_descriptor_rebound_bound_getattribute_cannot_reach_generator_frame_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
RESULT = getter("f_globals")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_globals"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_locals"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_locals")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_builtins")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_globals")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_globals")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_globals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_locals")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_locals":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_builtins")
    RESULT = getter(name=name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "f_builtins":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_locals")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_locals"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_locals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_builtins")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_builtins"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_builtins")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    name = Sneaky("f_globals")
    RESULT = getter(name)
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_globals"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
name = Sneaky("f_globals")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_globals"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_globals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_globals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_globals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_locals"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_locals_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_locals"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_locals_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_traceback_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

try:
    1 / 0
except Exception as exc:
    frame = exc.__traceback__.tb_frame

getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_traceback_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def compute():
    return 1

co = compute()
try:
    frame = co.cr_frame
    getter = frame.__getattribute__.__get__(None, type(frame))
    key = Sneaky("name")
    RESULT = getter(**{key: "f_builtins"})
finally:
    co.close()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_coroutine_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

async def produce():
    yield 1

ag = produce()
frame = ag.ag_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_async_generator_frame_builtins_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_getattribute_generator_frame_builtins_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

def make_gen():
    yield 1

gen = make_gen()
frame = gen.gi_frame
getter = frame.__getattribute__.__get__(None, type(frame))
key = Sneaky("name")
RESULT = getter(**{key: "f_builtins"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_getattribute_generator_frame_builtins_probe>",
        )


def test_descriptor_rebound_type_getattribute_cannot_reach_class_subclasses():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
RESULT = getter(Probe, "__subclasses__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_descriptor_rebound_type_getattribute_cannot_reach_class_mro():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
RESULT = getter(Probe, "__mro__")[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_descriptor_rebound_type_getattribute_cannot_reach_class_bases():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
RESULT = getter(Probe, "__bases__")[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_descriptor_rebound_type_getattribute_cannot_reach_class_base():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
RESULT = getter(Probe, "__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__subclasses__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_subclasses"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__mro__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_mro"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_bases"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__bases__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(Probe, name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__base__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__base__")
RESULT = getter(Probe, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_base"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__base__")
RESULT = getter(Probe, name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_subclasses"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(Probe, name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_mro"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_bases"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(Probe, name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__base__")
RESULT = getter(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_base"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
name = Sneaky("__base__")
RESULT = getter(Probe, name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(None, type(Probe))
key = Sneaky("name")
RESULT = getter(Probe, **{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_type_getattribute_class_base_probe>",
        )


def test_descriptor_rebound_bound_type_getattribute_cannot_reach_class_subclasses():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
RESULT = getter("__subclasses__")()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_descriptor_rebound_bound_type_getattribute_cannot_reach_class_mro():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
RESULT = getter("__mro__")[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_descriptor_rebound_bound_type_getattribute_cannot_reach_class_bases():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
RESULT = getter("__bases__")[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_descriptor_rebound_bound_type_getattribute_cannot_reach_class_base():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
RESULT = getter("__base__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__subclasses__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__mro__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__bases__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "__base__":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__base__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_subclasses"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_mro"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_bases"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_base"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__base__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__base__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_subclasses"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__subclasses__")
RESULT = getter(name=name)()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_mro"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__mro__")
RESULT = getter(name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_bases"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__bases__")
RESULT = getter(name=name)[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_base"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
name = Sneaky("__base__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_subclasses_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__subclasses__"})()
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_type_getattribute_class_subclasses_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_mro_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__mro__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_type_getattribute_class_mro_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_bases_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__bases__"})[0]
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_type_getattribute_class_bases_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_bound_type_getattribute_class_base_guard():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Sneaky(str):
    def __str__(self):
        return "not_name"

class Probe:
    pass

getter = type.__getattribute__.__get__(Probe, type(Probe))
key = Sneaky("name")
RESULT = getter(**{key: "__base__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_bound_type_getattribute_class_base_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_loader():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter("__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_spec():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter("__spec__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter("__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_loader_via_keyword_name():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter(name="__loader__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_loader_keyword_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_spec_via_keyword_name():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter(name="__spec__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_spec_keyword_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_dict_metadata_via_keyword_name():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
RESULT = getter(name="__dict__")
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_dict_keyword_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_loader_via_keyword_key():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
key = "name"
RESULT = getter(**{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_loader_keyword_key_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_spec_via_keyword_key():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
key = "name"
RESULT = getter(**{key: "__spec__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_spec_keyword_key_probe>",
        )


def test_descriptor_rebound_module_type_bound_getattribute_cannot_reach_module_dict_metadata_via_keyword_key():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

getter = type(math).__getattribute__.__get__(math, type(math))
key = "name"
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<descriptor_rebound_module_type_bound_getattribute_module_dict_keyword_key_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__spec__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__dict__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_loader"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__loader__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__spec__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__spec__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__loader__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_dict"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__dict__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__spec__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_stateful_str_subclass_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.calls = 0
        return obj

    def __hash__(self):
        self.calls += 1
        if self.calls <= 1:
            return 0
        return str.__hash__(self)

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__loader__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_positional_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_str_subclass_str_override_positional_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_spec"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__spec__")
RESULT = getter(name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_positional_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_stateful_str_subclass_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __new__(cls, value):
        obj = str.__new__(cls, value)
        obj.eq_calls = 0
        return obj

    __hash__ = str.__hash__

    def __eq__(self, other):
        if isinstance(other, str) and other == "name":
            self.eq_calls += 1
            return self.eq_calls > 1
        return str.__eq__(self, other)

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<stateful_str_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_loader_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_loader"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__loader__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_module_type_bound_getattribute_module_loader_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_spec_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_spec"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__spec__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_module_type_bound_getattribute_module_spec_probe>",
        )


def test_str_subclass_str_override_keyword_name_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_dict"

getter = type(math).__getattribute__.__get__(math, type(math))
name = Sneaky("__dict__")
RESULT = getter(name=name)
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_str_subclass_str_override_keyword_key_cannot_bypass_descriptor_rebound_module_type_bound_getattribute_module_dict_guard():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math

class Sneaky(str):
    def __str__(self):
        return "not_name"

getter = type(math).__getattribute__.__get__(math, type(math))
key = Sneaky("name")
RESULT = getter(**{key: "__dict__"})
"""
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            source,
            env=env,
            filename="<str_override_keyword_key_descriptor_rebound_module_type_bound_getattribute_module_dict_probe>",
        )


def test_traceback_code_object_rehydration_cannot_recover_importer_self(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{sandbox-escape}")
    source = f"""
F = type(getattr)
false = frozenset().__contains__

try:
    getattr(0, 1)
except Exception as exc:
    tb = exc.__traceback__
    i = 0
    while i < 7:
        tb = tb.tb_next
        i += 1
    norm_code = tb.tb_frame.f_code

try:
    getattr(0, "__self__")
except Exception as exc:
    tb = exc.__traceback__
    i = 0
    while i < 6:
        tb = tb.tb_next
        i += 1
    safe_code = tb.tb_frame.f_code
    guard_code = tb.tb_next.tb_frame.f_code

norm = F(norm_code, {{}})
guard = F(
    guard_code,
    {{
        "_normalize_attr_name": norm,
        "_allows_func_attr": false,
        "is_blocked_attr": false,
    }},
)
unsafe_getattr = F(
    safe_code,
    {{
        "_normalize_attr_name": norm,
        "_guard_attr_name_for_object": guard,
    }},
)

host = unsafe_getattr(__import__, "__self__")
host.allowed_imports = None

import builtins

RESULT = builtins.open({str(flag_path)!r}).read()
"""
    with pytest.raises((AttributeError, ImportError, TypeError)):
        run_raises(
            interp,
            source,
            env=env,
            filename="<traceback_code_object_rehydration_importer_self_probe>",
        )


def test_safe_builtin_wrapper_call_attribute_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            "RESULT = getattr.__call__",
            env=env,
            filename="<safe_builtin_wrapper_call_attr_probe>",
        )


def test_signature_from_callable_eval_str_cannot_mutate_safe_getattr_annotations(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{signature-eval-escape}")
    source = f"""
def h(y: int):
    pass

Sig = type(h.__signature__)
f = __builtins__["getattr"]
f.__annotations__ = {{"name": "open({str(flag_path)!r}).read()"}}
RESULT = Sig.from_callable(f, eval_str=True).parameters["name"].annotation
"""
    result = interp.run(
        source,
        env=env,
        filename="<signature_from_callable_eval_str_safe_getattr_annotation_probe>",
    )
    assert isinstance(result.exception, AttributeError)


def test_signature_from_callable_eval_str_cannot_mutate_user_function_annotate(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{annotate-eval-escape}")
    source = f"""
def h(y: int):
    pass

Sig = type(h.__signature__)
f = h.__annotate__
f.__annotations__ = {{"format": "open({str(flag_path)!r}).read()"}}
RESULT = Sig.from_callable(f, eval_str=True).parameters["format"].annotation
"""
    result = interp.run(
        source,
        env=env,
        filename="<signature_from_callable_eval_str_user_function_annotate_probe>",
    )
    assert isinstance(result.exception, AttributeError)


def test_host_module_function_annotations_cannot_be_reassigned():
    interp = Interpreter(allowed_imports={"inspect"})
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'import inspect\ninspect.unwrap.__annotations__ = {"func": "1 + 2"}',
            env=env,
            filename="<host_module_function_annotations_probe>",
        )


def test_host_module_annotations_cannot_be_reassigned():
    interp = Interpreter(allowed_imports={"inspect"})
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'import inspect\ninspect.__annotations__ = {"value": "1 + 2"}',
            env=env,
            filename="<host_module_annotations_probe>",
        )


def test_host_class_annotations_cannot_be_reassigned():
    interp = Interpreter(allowed_imports={"dataclasses"})
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'import dataclasses\ndataclasses.Field.__annotations__ = {"value": "1 + 2"}',
            env=env,
            filename="<host_class_annotations_probe>",
        )


def test_host_env_function_annotations_cannot_be_reassigned():
    def helper(value):
        return value

    interp = Interpreter(allowed_imports={"inspect"})
    env = interp.make_default_env({"HELPER": helper})
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'HELPER.__annotations__ = {"value": "1 + 2"}',
            env=env,
            filename="<host_env_function_annotations_probe>",
        )


def test_host_env_instance_method_annotations_cannot_be_reassigned():
    class Helper:
        def probe(self, value):
            return value

    interp = Interpreter(allowed_imports={"inspect"})
    env = interp.make_default_env({"HELPER": Helper()})
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'HELPER.probe.__annotations__ = {"value": "1 + 2"}',
            env=env,
            filename="<host_env_instance_method_annotations_probe>",
        )


def test_signature_from_callable_eval_str_cannot_mutate_host_env_function_annotations():
    def helper(value):
        return value

    interp = Interpreter(allowed_imports={"inspect"})
    env = interp.make_default_env({"HELPER": helper})
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            """
import inspect
Sig = type((lambda: None).__signature__)
HELPER.__annotations__ = {"value": "1 + 2"}
RESULT = Sig.from_callable(HELPER, eval_str=True).parameters["value"].annotation
""",
            env=env,
            filename="<signature_from_callable_eval_str_host_env_function_probe>",
        )


def test_host_function_annotations_mapping_cannot_drive_signature_eval_str_in_place(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{host-annotations-mapping-escape}")
    with pytest.raises(TypeError):
        run_raises(
            interp,
            f"""
def h():
    pass

host = type(h.__signature__).bind
host.__annotations__["self"] = "I.__self__._restricted_import.__globals__['__builtins__']['open']({str(flag_path)!r}).read()"
""",
            env=env,
            filename="<host_function_annotations_mapping_probe>",
        )


def test_vars_host_module_annotations_mapping_is_read_only():
    module = ModuleType("helper_mod")
    module.__annotations__ = {"value": int}
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env({"MOD": module})
    with pytest.raises(TypeError):
        run_raises(
            interp,
            """
vars(MOD)["__annotations__"]["value"] = "1 + 2"
""",
            env=env,
            filename="<vars_host_module_annotations_mapping_probe>",
        )


def test_imported_host_instance_method_annotations_cannot_be_reassigned():
    interp = Interpreter(allowed_imports={"pathlib"})
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            'import pathlib\npath = pathlib.Path(".")\npath.match.__annotations__ = {"pattern": "1 + 2"}',
            env=env,
            filename="<imported_host_instance_method_annotations_probe>",
        )


@pytest.mark.parametrize(
    "attr_name",
    (
        "builtins",
        "closure",
        "code",
        "globals",
        "node",
        "scope_info",
    ),
)
def test_user_function_internal_attrs_are_blocked(attr_name: str):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env({"ATTR_NAME": attr_name})
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            """
def f():
    pass

RESULT = getattr(f, ATTR_NAME)
""",
            env=env,
            filename=f"<user_function_internal_attr_{attr_name}_probe>",
        )


def test_user_function_getstate_escape_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    with pytest.raises(AttributeError):
        run_raises(
            interp,
            """
def f():
    pass

RESULT = type(f).__getstate__(f)
""",
            env=env,
            filename="<user_function_getstate_probe>",
        )


@pytest.mark.skipif(not HAS_HOST_ANNOTATE, reason="host __annotate__ requires Python 3.14+")
def test_host_function_annotate_cannot_be_reassigned_to_drive_signature_eval_str(tmp_path: Path):
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    flag_path = tmp_path / "flag.txt"
    flag_path.write_text("FLAG{host-annotate-escape}")
    source = f"""
def h():
    pass

host = type(h.__signature__).bind
host.__annotate__ = lambda _: {{
    "self": "HOST.__globals__['__builtins__']['open']({str(flag_path)!r}).read()"
}}
Sig = type(h.__signature__)
RESULT = Sig.from_callable(host, eval_str=True, globals={{"HOST": host}}).parameters["self"].annotation
"""
    result = interp.run(
        source,
        env=env,
        filename="<host_function_annotate_signature_eval_str_probe>",
    )
    assert isinstance(result.exception, AttributeError)
