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
        interp.run(
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
        interp.run(
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
        interp.run(source, env=env, filename="<traceback_frame_probe>")


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
        interp.run(
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
        interp.run(
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
        interp.run(source, env=env, filename="<traceback_frame_builtins_probe>")


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
        interp.run(source, env=env, filename="<traceback_tb_next_frame_locals_probe>")


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
        interp.run(source, env=env, filename="<traceback_f_back_frame_globals_probe>")


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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(source, env=env, filename="<exception_context_traceback_probe>")


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
        interp.run(source, env=env, filename="<exception_cause_traceback_probe>")


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
        interp.run(
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
        interp.run(source, env=env, filename="<coroutine_frame_locals_probe>")


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


def test_function_globals_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

RESULT = f.__globals__["__builtins__"]
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<function_globals_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_globals_probe>")


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
        interp.run(source, env=env, filename="<setattr_dunder_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_setattr_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_setattr_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_setattr_probe>")


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
        interp.run(source, env=env, filename="<delattr_dunder_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_delattr_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_delattr_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_delattr_probe>")


def test_function_code_object_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
def f():
    return 1

RESULT = f.__code__.co_consts
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<function_code_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_code_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_code_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_code_probe>")


def test_builtin_callable_self_module_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
builtins_mod = len.__self__
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<builtin_callable_self_probe>")


def test_object_getattribute_cannot_reach_builtin_callable_self_module():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
builtins_mod = getter(len, "__self__")
RESULT = builtins_mod.open
"""
    with pytest.raises(AttributeError):
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<type_getattribute_builtin_callable_self_probe>",
        )


def test_import_callable_self_interpreter_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
host = __import__.__self__
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<import_callable_self_probe>")


def test_object_getattribute_cannot_reach_import_callable_self_interpreter():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
host = getter(__import__, "__self__")
RESULT = host.allowed_imports
"""
    with pytest.raises(AttributeError):
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<stateful_str_super_getattribute_import_callable_self_probe>",
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(source, env=env, filename="<import_callable_func_globals_probe>")


def test_object_getattribute_cannot_reach_import_callable_func_globals():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
getter = object.__getattribute__
func = getter(__import__, "__func__")
RESULT = getter(func, "__globals__")["__builtins__"]
"""
    with pytest.raises(AttributeError):
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<super_getattribute_import_callable_func_globals_probe>",
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
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<super_getattribute_class_subclasses_probe>",
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
        interp.run(source, env=env, filename="<class_base_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_class_base_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_class_base_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_class_base_probe>")


def test_class_bases_escape_chain_is_blocked():
    interp = Interpreter(allowed_imports=set())
    env = interp.make_default_env()
    source = """
class Probe:
    pass

RESULT = Probe.__bases__
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<class_bases_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_class_bases_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_class_bases_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_class_bases_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_class_mro_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_class_mro_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_class_mro_probe>")


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
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<super_getattribute_closure_cell_probe>",
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
        interp.run(source, env=env, filename="<reduce_hook_probe>")


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
        interp.run(source, env=env, filename="<reduce_probe>")


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
        interp.run(source, env=env, filename="<object_getattribute_reduce_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_reduce_hook_probe>")


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
        interp.run(source, env=env, filename="<type_getattribute_reduce_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_reduce_hook_probe>")


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
        interp.run(source, env=env, filename="<super_getattribute_reduce_probe>")


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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<stateful_str_type_getattribute_generator_frame_probe>",
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(source, env=env, filename="<module_loader_import_smuggling_probe>")


def test_module_spec_import_smuggling_chain_is_blocked():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
spec = math.__spec__
RESULT = spec.loader.load_module("os")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<module_spec_import_smuggling_probe>")


def test_module_dict_import_smuggling_chain_is_blocked():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
module_dict = math.__dict__
RESULT = module_dict["__loader__"].load_module("os")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<module_dict_import_smuggling_probe>")


def test_object_getattribute_cannot_reach_module_loader_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = object.__getattribute__
RESULT = getter(math, "__loader__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<object_getattribute_module_loader_probe>")


def test_object_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = object.__getattribute__
RESULT = getter(math, "__dict__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<object_getattribute_module_dict_probe>")


def test_super_getattribute_cannot_reach_module_dict_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = super(type(math), math).__getattribute__
RESULT = getter("__dict__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<super_getattribute_module_dict_probe>")


def test_type_getattribute_cannot_reach_module_spec_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = type.__getattribute__
RESULT = getter(math, "__spec__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<type_getattribute_module_spec_probe>")


def test_super_getattribute_cannot_reach_module_loader_metadata():
    interp = Interpreter(allowed_imports={"math"})
    env = interp.make_default_env()
    source = """
import math
getter = super(type(math), math).__getattribute__
RESULT = getter("__loader__")
"""
    with pytest.raises(AttributeError):
        interp.run(source, env=env, filename="<super_getattribute_module_loader_probe>")


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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<stateful_str_keyword_type_getattribute_module_dict_probe>",
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
        interp.run(
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
        interp.run(
            source,
            env=env,
            filename="<str_override_keyword_super_getattribute_module_dict_probe>",
        )
