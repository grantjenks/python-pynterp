from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

from pynterp import Interpreter

HAS_TEMPLATE_STR = hasattr(ast, "TemplateStr")
HAS_TYPE_ALIAS = hasattr(ast, "TypeAlias")
HAS_TYPE_PARAMS = hasattr(ast.parse("def f():\n    pass").body[0], "type_params")
if HAS_TEMPLATE_STR:
    import string.templatelib as templatelib

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


def test_lambda_closure_and_defaults(run_interpreter):
    source = """
def outer():
    factor = 2
    fn = lambda x, y=3, *, z=4: (x + y) * factor + z
    factor = 5
    return fn(1), fn(1, z=1)

RESULT = outer()
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (24, 21)


def test_multiple_lambdas_on_same_line(run_interpreter):
    source = """
f, g = (lambda x: x + 1, lambda y: y * 2)
RESULT = (f(3), g(4))
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (4, 8)


def test_lambda_missing_required_argument_name(run_interpreter):
    source = """
fn = lambda value: value
fn()
"""
    with pytest.raises(TypeError, match=r"<lambda>\(\) missing required argument 'value'"):
        run_interpreter(source)


def test_namedexpr_assigns_and_returns_value(run_interpreter):
    source = """
total = (value := 40) + 2
RESULT = (total, value)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (42, 40)


def test_namedexpr_in_comprehension_binds_outer_scope(run_interpreter):
    source = """
marker = -1
values = [(marker := i) for i in range(4) if (marker := i) % 2 == 0]
nested = [[(marker := j) for j in range(2)] for _ in range(1)]
RESULT = (values, nested, marker)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ([0, 2], [[0, 1]], 1)


def test_typing_runtime_factories_use_interpreted_module_name(run_interpreter):
    source = """
from typing import NewType, ParamSpec, TypeVar, TypeVarTuple

T = TypeVar("T")
P = ParamSpec("P")
Ts = TypeVarTuple("Ts")
Alias = NewType("Alias", int)
RESULT = (T.__module__, P.__module__, Ts.__module__, Alias.__module__)
"""
    env = run_interpreter(source, env={"__name__": "demo_typing_module"})
    assert env["RESULT"] == ("demo_typing_module",) * 4


def test_genericalias_pickle_with_typevar_succeeds(run_interpreter):
    source = """
import pickle
from typing import TypeVar

T = TypeVar("T")
PAYLOAD = pickle.dumps(list[T], protocol=0)
ROUNDTRIP = pickle.loads(PAYLOAD)
RESULT = (isinstance(PAYLOAD, (bytes, bytearray)), str(ROUNDTRIP))
"""
    import sys
    import types

    module_name = "test_pickle_genericalias_mod"
    module = types.ModuleType(module_name)
    env = module.__dict__
    env.update(
        {
            "__name__": module_name,
            "__package__": None,
            "__file__": "<test_pickle_genericalias>",
            "__builtins__": dict(builtins.__dict__),
        }
    )

    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
        interpreter.run(source, env=env, filename="<test_pickle_genericalias>")
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    assert env["RESULT"] == (True, "list[~T]")


def test_user_function_pickle_roundtrip_succeeds():
    source = """
import pickle

def global_pos_only_f(a, b, /):
    return a, b

PAYLOAD = pickle.dumps(global_pos_only_f, protocol=0)
ROUNDTRIP = pickle.loads(PAYLOAD)
RESULT = (
    isinstance(PAYLOAD, (bytes, bytearray)),
    ROUNDTRIP is global_pos_only_f,
    ROUNDTRIP(1, 2),
)
"""
    import sys
    import types

    module_name = "test_pickle_user_function_mod"
    module = types.ModuleType(module_name)
    env = module.__dict__
    env.update(
        {
            "__name__": module_name,
            "__package__": None,
            "__file__": "<test_pickle_user_function>",
            "__builtins__": dict(builtins.__dict__),
        }
    )

    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
        interpreter.run(source, env=env, filename="<test_pickle_user_function>")
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous

    assert env["RESULT"] == (True, True, (1, 2))


def test_generic_alias_base_resolves_to_origin_type(run_interpreter):
    source = """
class C(list[int]):
    pass

RESULT = (issubclass(C, list), isinstance(C([1]), list), C.__class__ is type)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (True, True, True)


def test_local_class_qualname_in_method_scope(run_interpreter):
    source = """
class Outer:
    def make(self):
        class Local(list):
            pass
        return Local.__qualname__

RESULT = Outer().make()
"""
    env = run_interpreter(source)
    assert env["RESULT"] == "Outer.make.<locals>.Local"


def test_init_subclass_defined_in_interpreted_class_is_implicitly_classmethod(run_interpreter):
    source = """
class Base:
    seen = None
    def __init_subclass__(cls):
        Base.seen = cls.__name__
        cls.marker = "ok"

class Child(Base):
    pass

RESULT = (Base.seen, Child.marker)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("Child", "ok")


def test_class_getitem_defined_in_interpreted_class_is_implicitly_classmethod(run_interpreter):
    source = """
class Box:
    def __class_getitem__(cls, item):
        return (cls.__name__, item.__name__)

RESULT = Box[int]
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("Box", "int")


def test_class_private_slot_attribute_access_is_name_mangled(run_interpreter):
    source = """
class Rat:
    __slots__ = ["_Rat__num"]

    def __init__(self, value):
        self.__num = value

    def num(self):
        return self.__num

    def bump(self):
        self.__num += 1
        return self.__num

r = Rat(2)
RESULT = (r.num(), r.bump(), hasattr(r, "_Rat__num"), hasattr(r, "__num"))
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (2, 3, True, False)


@pytest.mark.skipif(not HAS_TYPE_ALIAS, reason="TypeAlias requires Python 3.12+")
def test_typealias_statement_builds_runtime_alias_with_params(run_interpreter):
    source = """
from typing import Callable
type X[**P] = Callable[P, int]
generic = X[[str]]
RESULT = (
    type(X).__name__,
    X.__module__,
    len(X.__type_params__),
    generic.__args__,
    generic.__parameters__,
)
"""
    env = run_interpreter(source, env={"__name__": "demo_typealias_module"})
    assert env["RESULT"] == (
        "TypeAliasType",
        "demo_typealias_module",
        1,
        ([str],),
        (),
    )


@pytest.mark.skipif(not HAS_TYPE_ALIAS, reason="TypeAlias requires Python 3.12+")
def test_typealias_type_params_do_not_leak_to_scope(run_interpreter):
    source = """
type Alias[T] = tuple[T]
try:
    T
except NameError:
    leaked = False
else:
    leaked = True
RESULT = (Alias[int].__args__, leaked)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ((int,), False)


def test_user_function_exposes_empty_type_params_by_default(run_interpreter):
    source = """
def f():
    return 42

RESULT = f.__type_params__
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ()


@pytest.mark.skipif(not HAS_TYPE_PARAMS, reason="Type params require Python 3.12+")
def test_generic_function_records_type_params_without_scope_leak(run_interpreter):
    source = """
def f[T](value: T):
    return value

T_param, = f.__type_params__
try:
    T
except NameError:
    leaked = False
else:
    leaked = True

RESULT = (T_param.__name__, f(7), leaked)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("T", 7, False)


def test_async_function_def_returns_coroutine(run_interpreter):
    source = """
async def add(x, y=3):
    return x + y

CORO = add(4)
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    assert hasattr(coro, "__await__")
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == 7


def test_await_expression_uses_custom_awaitable(run_interpreter):
    source = """
class Ready:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        if False:
            yield None
        return self.value

async def run():
    value = await Ready(41)
    return value + 1

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == 42


def test_await_exception_can_be_handled_in_async_function(run_interpreter):
    source = """
class Boom:
    def __await__(self):
        raise ValueError("boom")
        yield None

async def run():
    try:
        await Boom()
    except ValueError as exc:
        return str(exc)
    return "miss"

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == "boom"


def test_async_function_def_works_in_generator_execution_path(run_interpreter):
    source = """
def outer():
    async def inner(value):
        return value + 1
    yield inner

INNER = next(outer())
CORO = INNER(9)
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == 10


def test_async_with_calls_aenter_and_aexit(run_interpreter):
    source = """
EVENTS = []

class Manager:
    async def __aenter__(self):
        EVENTS.append(("enter", 5))
        return 5

    async def __aexit__(self, exc_type, exc, tb):
        EVENTS.append(("exit", exc_type.__name__ if exc_type else None))
        return False

async def run():
    async with Manager() as value:
        return value + 1

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == 6
    assert env["EVENTS"] == [("enter", 5), ("exit", None)]


def test_async_with_can_suppress_exception(run_interpreter):
    source = """
EVENTS = []

class Suppressor:
    async def __aenter__(self):
        EVENTS.append("enter")
        return "token"

    async def __aexit__(self, exc_type, exc, tb):
        EVENTS.append(exc_type.__name__ if exc_type else None)
        return exc_type is ValueError

async def run():
    async with Suppressor():
        raise ValueError("boom")
    return "ok"

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(StopIteration) as exc_info:
        coro.send(None)
    assert exc_info.value.value == "ok"
    assert env["EVENTS"] == ["enter", "ValueError"]


def test_async_with_requires_aexit_method(run_interpreter):
    source = """
BODY = None

class MissingExit:
    async def __aenter__(self):
        return "token"

async def run():
    global BODY
    BODY = False
    async with MissingExit():
        BODY = True

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(TypeError, match=r"asynchronous context manager.*__aexit__"):
        coro.send(None)
    assert env["BODY"] is False


def test_async_with_requires_aenter_method(run_interpreter):
    source = """
BODY = None

class MissingEnter:
    async def __aexit__(self, exc_type, exc, tb):
        return False

async def run():
    global BODY
    BODY = False
    async with MissingEnter():
        BODY = True

CORO = run()
"""
    env = run_interpreter(source)
    coro = env["CORO"]
    with pytest.raises(TypeError, match=r"asynchronous context manager.*__aenter__"):
        coro.send(None)
    assert env["BODY"] is False


def test_async_with_rejects_non_awaitable_enter_and_exit_values(run_interpreter):
    source = """
class BadEnter:
    def __aenter__(self):
        return 123

    async def __aexit__(self, exc_type, exc, tb):
        return False

class BadExit:
    async def __aenter__(self):
        return "ok"

    def __aexit__(self, exc_type, exc, tb):
        return 456

async def run_enter():
    async with BadEnter():
        return "body"

async def run_exit():
    async with BadExit():
        return "body"

CORO_ENTER = run_enter()
CORO_EXIT = run_exit()
"""
    env = run_interpreter(source)

    with pytest.raises(
        TypeError,
        match=r"'async with' received an object from __aenter__ that does not implement __await__: int",
    ):
        env["CORO_ENTER"].send(None)

    with pytest.raises(
        TypeError,
        match=r"'async with' received an object from __aexit__ that does not implement __await__: int",
    ):
        env["CORO_EXIT"].send(None)


def test_async_for_supports_loop_control_and_else(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)
        self.aiter_calls = 0

    def __aiter__(self):
        self.aiter_calls += 1
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

async def run_break():
    counter = AsyncCounter([1, 2, 3, 4])
    total = 0
    async for value in counter:
        if value == 2:
            continue
        total += value
        if value == 3:
            break
    else:
        total += 100
    return (total, counter.aiter_calls)

async def run_else():
    counter = AsyncCounter([1, 2, 3])
    total = 0
    async for value in counter:
        total += value
    else:
        total += 100
    return (total, counter.aiter_calls)

CORO_BREAK = run_break()
CORO_ELSE = run_else()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as break_info:
        env["CORO_BREAK"].send(None)
    with pytest.raises(StopIteration) as else_info:
        env["CORO_ELSE"].send(None)
    assert break_info.value.value == (4, 1)
    assert else_info.value.value == (106, 1)


def test_async_for_requires_aiter_method(run_interpreter):
    source = """
async def run():
    async for _ in (1, 2, 3):
        pass

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(TypeError, match="async for'.*__aiter__.*tuple"):
        env["CORO"].send(None)


def test_async_for_invalid_anext_awaitable_sets_cause(run_interpreter):
    source = """
class Bad:
    def __aiter__(self):
        return self

    def __anext__(self):
        return self

    def __await__(self):
        1 / 0
        yield None

async def run():
    async for _ in Bad():
        pass

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(TypeError, match="invalid object from __anext__") as exc_info:
        env["CORO"].send(None)
    assert isinstance(exc_info.value.__cause__, ZeroDivisionError)


def test_async_list_set_dict_comprehensions(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)
        self.aiter_calls = 0

    def __aiter__(self):
        self.aiter_calls += 1
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

class Ready:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        if False:
            yield None
        return self.value

async def run():
    counter = AsyncCounter([1, 2, 3, 4])
    list_result = [await Ready(value * 2) async for value in counter if value % 2 == 0]
    set_result = {value async for value in AsyncCounter([1, 2, 2, 3])}
    dict_result = {value: await Ready(value + 10) async for value in AsyncCounter([1, 3])}
    return (list_result, set_result, dict_result, counter.aiter_calls)

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as exc_info:
        env["CORO"].send(None)
    assert exc_info.value.value == ([4, 8], {1, 2, 3}, {1: 11, 3: 13}, 1)


def test_async_generator_expression_produces_async_iterator(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

async def run():
    gen = (value * 3 async for value in AsyncCounter([1, 2, 3]) if value != 2)
    values = []
    async for value in gen:
        values.append(value)
    return (values, hasattr(gen, "__aiter__"), hasattr(gen, "__anext__"))

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as exc_info:
        env["CORO"].send(None)
    assert exc_info.value.value == ([3, 9], True, True)


def test_generator_expression_with_nested_async_comprehension_is_async(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

async def run():
    gen = ([value + offset async for value in AsyncCounter([1, 2])] for offset in [10, 20])
    buckets = []
    async for values in gen:
        buckets.append(values)
    return (buckets, hasattr(gen, "__aiter__"), hasattr(gen, "__anext__"))

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as exc_info:
        env["CORO"].send(None)
    assert exc_info.value.value == ([[11, 12], [21, 22]], True, True)


def test_generator_expression_yielding_async_generators_stays_sync_iterable(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

async def run():
    gens = ((value async for value in AsyncCounter(range(limit))) for limit in [3, 5])
    values = [item for gen in gens async for item in gen]
    return (values, hasattr(gens, "__iter__"), hasattr(gens, "__aiter__"))

CORO = run()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as exc_info:
        env["CORO"].send(None)
    assert exc_info.value.value == ([0, 1, 2, 0, 1, 2, 3, 4], True, False)


def test_async_comprehension_works_in_generator_execution_path(run_interpreter):
    source = """
class AsyncCounter:
    def __init__(self, values):
        self.values = list(values)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for value in self.values:
            yield value

def outer():
    async def run():
        return [value async for value in AsyncCounter([1, 2, 3])]
    yield run

RUN = next(outer())
CORO = RUN()
"""
    env = run_interpreter(source)
    with pytest.raises(StopIteration) as exc_info:
        env["CORO"].send(None)
    assert exc_info.value.value == [1, 2, 3]


def test_async_generator_produces_values(run_interpreter):
    source = """
async def numbers():
    yield 1
    yield 2

AGEN = numbers()
"""
    env = run_interpreter(source)
    agen = env["AGEN"]
    assert agen.__aiter__() is agen
    with pytest.raises(StopIteration) as first:
        agen.__anext__().send(None)
    assert first.value.value == 1
    with pytest.raises(StopIteration) as second:
        agen.__anext__().send(None)
    assert second.value.value == 2
    with pytest.raises(StopAsyncIteration):
        agen.__anext__().send(None)


def test_async_generator_asend_passes_values_to_yield_expression(run_interpreter):
    source = """
async def echo():
    incoming = yield "start"
    yield incoming

AGEN = echo()
"""
    env = run_interpreter(source)
    agen = env["AGEN"]
    with pytest.raises(StopIteration) as first:
        agen.__anext__().send(None)
    assert first.value.value == "start"
    with pytest.raises(StopIteration) as second:
        agen.asend("next").send(None)
    assert second.value.value == "next"
    with pytest.raises(StopAsyncIteration):
        agen.__anext__().send(None)


def test_async_generator_supports_await_in_body(run_interpreter):
    source = """
class Ready:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        if False:
            yield None
        return self.value

async def values():
    yield await Ready(3)
    yield await Ready(4)

AGEN = values()
"""
    env = run_interpreter(source)
    agen = env["AGEN"]
    with pytest.raises(StopIteration) as first:
        agen.__anext__().send(None)
    assert first.value.value == 3
    with pytest.raises(StopIteration) as second:
        agen.__anext__().send(None)
    assert second.value.value == 4
    with pytest.raises(StopAsyncIteration):
        agen.__anext__().send(None)


def test_async_generator_wraps_stopasynciteration_as_runtimeerror(run_interpreter):
    source = """
class BadTarget:
    def __setitem__(self, key, value):
        raise StopAsyncIteration(42)

TARGET = BadTarget()

async def source():
    yield 10

async def run():
    gen = (0 async for TARGET[0] in source())
    await gen.asend(None)

CORO = run()
"""
    env = run_interpreter(source, env={"StopAsyncIteration": StopAsyncIteration})
    with pytest.raises(RuntimeError, match="async generator raised StopAsyncIteration") as exc_info:
        env["CORO"].send(None)
    assert isinstance(exc_info.value.__cause__, StopAsyncIteration)
    assert exc_info.value.__cause__.args == (42,)


def test_async_generator_aclose_runs_finally_block(run_interpreter):
    source = """
EVENTS = []

async def stream():
    try:
        yield 1
        yield 2
    finally:
        EVENTS.append("closed")

AGEN = stream()
"""
    env = run_interpreter(source)
    agen = env["AGEN"]
    with pytest.raises(StopIteration) as first:
        agen.__anext__().send(None)
    assert first.value.value == 1
    with pytest.raises(StopIteration) as close_result:
        agen.aclose().send(None)
    assert close_result.value.value is None
    assert env["EVENTS"] == ["closed"]
    with pytest.raises(StopAsyncIteration):
        agen.__anext__().send(None)


def test_namedexpr_works_in_generator_execution_path(run_interpreter):
    source = """
def run():
    total = 0
    yield (total := total + 1)
    yield total

RESULT = list(run())
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [1, 1]


def test_bare_raise_without_active_exception_raises_runtimeerror(run_interpreter):
    with pytest.raises(RuntimeError, match="No active exception to reraise"):
        run_interpreter("raise")


def test_bare_raise_reraises_caught_exception(run_interpreter):
    source = """
try:
    raise ValueError("boom")
except ValueError:
    raise
"""
    with pytest.raises(ValueError, match="boom"):
        run_interpreter(source)


def test_bare_raise_reraises_caught_exception_in_generator_path(run_interpreter):
    source = """
def run():
    try:
        raise ValueError("boom")
    except ValueError:
        raise
    yield "unreachable"

GEN = run()
"""
    env = run_interpreter(source)
    with pytest.raises(ValueError, match="boom"):
        next(env["GEN"])


def test_trystar_wraps_single_exception_in_group(run_interpreter):
    source = """
try:
    raise ValueError("boom")
except* ValueError as exc:
    RESULT = (
        type(exc).__name__,
        len(exc.exceptions),
        type(exc.exceptions[0]).__name__,
        str(exc.exceptions[0]),
    )
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("ExceptionGroup", 1, "ValueError", "boom")


def test_trystar_splits_and_reraises_unhandled_group_members(run_interpreter):
    source = """
try:
    try:
        raise ExceptionGroup("group", [ValueError("a"), TypeError("b")])
    except* ValueError as exc:
        handled = [type(item).__name__ for item in exc.exceptions]
except ExceptionGroup as exc:
    remaining = [type(item).__name__ for item in exc.exceptions]

RESULT = (handled, remaining)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (["ValueError"], ["TypeError"])


def test_trystar_works_in_generator_execution_path(run_interpreter):
    source = """
def run():
    try:
        raise ExceptionGroup("group", [ValueError("a"), TypeError("b")])
    except* ValueError as exc:
        yield ("value", [type(item).__name__ for item in exc.exceptions])
    except* TypeError as exc:
        yield ("type", [type(item).__name__ for item in exc.exceptions])

RESULT = list(run())
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [("value", ["ValueError"]), ("type", ["TypeError"])]


def test_trystar_rejects_exceptiongroup_handler_type(run_interpreter):
    source = """
try:
    raise ExceptionGroup("group", [ValueError("x")])
except* ExceptionGroup:
    pass
    """
    with pytest.raises(
        TypeError, match=r"catching ExceptionGroup with except\* is not allowed"
    ):
        run_interpreter(source)


def test_match_supports_common_pattern_forms(run_interpreter):
    source = """
class Point:
    __match_args__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y

subjects = [
    None,
    (0, 1, 2),
    {"a": 1, "b": 2},
    Point(3, 4),
    2,
    "abc",
]
results = []
for item in subjects:
    match item:
        case None:
            results.append("none")
        case [0, *tail]:
            results.append(("seq", tail))
        case {"a": value, **rest}:
            results.append(("map", value, rest))
        case Point(x, y):
            results.append(("class", x + y))
        case 1 | 2 | 3 as number:
            results.append(("or", number))
        case str(text):
            results.append(("str", text))

RESULT = results
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [
        "none",
        ("seq", [1, 2]),
        ("map", 1, {"b": 2}),
        ("class", 7),
        ("or", 2),
        ("str", "abc"),
    ]


def test_match_guard_false_keeps_capture_bindings(run_interpreter):
    source = """
class A:
    VALUE = 0

match 0:
    case x if x:
        outcome = "first"
    case _ as y if y == x and y:
        outcome = "second"
    case A.VALUE:
        outcome = "third"

RESULT = (x, y, outcome)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (0, 0, "third")


def test_match_works_in_generator_execution_path(run_interpreter):
    source = """
def classify(values):
    for item in values:
        match item:
            case 0:
                yield "zero"
            case _:
                yield "other"

RESULT = list(classify([0, 1, 0]))
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ["zero", "other", "zero"]


def test_augassign_supports_attribute_and_subscript_targets(run_interpreter):
    source = """
class Box:
    def __init__(self):
        self.items = [1, 2]

box = Box()
alias = box.items
box.items += [3]

nums = [10]
nums[0] += 5

RESULT = (box.items, alias, nums, alias is box.items)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ([1, 2, 3], [1, 2, 3], [15], True)


def test_augassign_works_in_generator_execution_path(run_interpreter):
    source = """
class Box:
    def __init__(self):
        self.total = 1

def run():
    box = Box()
    values = [4]
    box.total += 2
    values[0] += 3
    yield box.total, values[0]

RESULT = list(run())
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [(3, 7)]


def test_starred_expression_supports_collection_literals(run_interpreter):
    source = """
values = (2, 3)
RESULT = (
    [1, *values, 4],
    (0, *values, 5),
    {1, *values, 6},
)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ([1, 2, 3, 4], (0, 2, 3, 5), {1, 2, 3, 6})


def test_starred_assignment_target_unpacks_values(run_interpreter):
    source = """
first, *middle, last = range(6)
[left, *rest] = [10, 20, 30, 40]
RESULT = (first, middle, last, left, rest)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (0, [1, 2, 3, 4], 5, 10, [20, 30, 40])


def test_starred_assignment_works_in_generator_execution_path(run_interpreter):
    source = """
def run():
    head, *body, tail = [1, 2, 3, 4]
    yield head, body, tail

RESULT = list(run())
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [(1, [2, 3], 4)]


def test_attr_guard_allows_module_metadata_and_bound_method_func(run_interpreter):
    source = """
import math

class Box:
    def value(self):
        return 42

box = Box()
RESULT = (
    math.__spec__ is not None,
    math.__loader__ is not None,
    getattr(math, "__spec__") is math.__spec__,
    hasattr(math, "__loader__"),
    box.value.__func__.__name__,
)
"""
    env = run_interpreter(source, allowed_imports={"math"})
    assert env["RESULT"] == (True, True, True, True, "value")


def test_bound_method_allows_keyword_named_self(run_interpreter):
    source = """
class Box:
    def capture(instance, **kwargs):
        return (instance.value, kwargs["self"])

box = Box()
box.value = "bound"
RESULT = box.capture(self="keyword")
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("bound", "keyword")


def test_attr_guard_allows_traceback_but_keeps_tb_frame_blocked(run_interpreter):
    source = """
try:
    1 / 0
except Exception as exc:
    tb = exc.__traceback__
    try:
        _ = tb.tb_frame
    except Exception as blocked:
        RESULT = (tb is not None, type(blocked).__name__, str(blocked))
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (
        True,
        "AttributeError",
        "attribute access to 'tb_frame' is blocked in this environment",
    )


def test_attr_guard_allows_coroutine_frame_and_f_back(run_interpreter):
    source = """
async def compute():
    return 1

co = compute()
frame = co.cr_frame
try:
    _ = frame.f_globals
except Exception as blocked:
    BLOCKED = (type(blocked).__name__, str(blocked))
else:
    BLOCKED = None
co.close()
RESULT = (frame is not None, frame.f_back is None, BLOCKED)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (
        True,
        True,
        (
            "AttributeError",
            "attribute access to 'f_globals' is blocked in this environment",
        ),
    )


def test_attr_guard_allows_coroutine_frame_in_generator_execution_path(run_interpreter):
    source = """
async def compute():
    return 1

def run():
    co = compute()
    frame = co.cr_frame
    try:
        _ = frame.f_builtins
    except Exception as blocked:
        blocked_info = (type(blocked).__name__, str(blocked))
    else:
        blocked_info = None
    co.close()
    yield (frame is not None, frame.f_back is None, blocked_info)

RESULT = list(run())
"""
    env = run_interpreter(source)
    assert env["RESULT"] == [
        (
            True,
            True,
            (
                "AttributeError",
                "attribute access to 'f_builtins' is blocked in this environment",
            ),
        )
    ]


def test_attr_guard_allows_class_bases_but_blocks_subclasses(run_interpreter):
    source = """
class Derived(list):
    pass

try:
    _ = list.__subclasses__
except Exception as blocked:
    BLOCKED = (type(blocked).__name__, str(blocked))

RESULT = (Derived.__bases__[0] is list, BLOCKED)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == (
        True,
        (
            "AttributeError",
            "attribute access to '__subclasses__' is blocked in this environment",
        ),
    )


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


def test_import_dotted_module_as_alias_binds_leaf_module():
    source = """
import unittest.mock as mock
import xml.parsers.expat.errors as ERRORS
RESULT = (
    mock.__name__,
    hasattr(mock, "patch"),
    ERRORS.__name__.endswith(".errors"),
    hasattr(ERRORS, "codes"),
)
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "__main__",
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename="<import_asname>")
    assert env["RESULT"] == ("unittest.mock", True, True, True)


def test_import_dotted_module_without_alias_binds_top_level_name():
    source = """
import xml.parsers.expat.errors
RESULT = (xml.__name__, hasattr(xml, "parsers"))
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "__main__",
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename="<import_top_level>")
    assert env["RESULT"] == ("xml", True)


def test_importlib_metadata_available_without_importlib_import_module(run_interpreter):
    source = """
import importlib.metadata
import importlib.metadata as metadata_alias

RESULT = (
    importlib.__name__,
    importlib.metadata.__name__,
    metadata_alias is importlib.metadata,
    hasattr(importlib.metadata, "version"),
    hasattr(importlib, "import_module"),
)
"""
    env = run_interpreter(source)
    assert env["RESULT"] == ("importlib", "importlib.metadata", True, True, False)


def test_interpreters_run_func_accepts_interpreted_function():
    pytest.importorskip("_interpreters")
    source = """
from test.support import import_helper
import os

_interpreters = import_helper.import_module("_interpreters")
interp = _interpreters.create()
r, w = os.pipe()

def script():
    global w
    import contextlib
    with open(w, "w", encoding="utf-8") as spipe:
        with contextlib.redirect_stdout(spipe):
            print("it worked!", end="")

try:
    _interpreters.set___main___attrs(interp, dict(w=w))
    _interpreters.run_func(interp, script)
    with open(r, encoding="utf-8") as outfile:
        RESULT = outfile.read()
finally:
    _interpreters.destroy(interp)
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "__main__",
        "__package__": None,
        "__file__": "<interpreters_run_func_ok>",
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename="<interpreters_run_func_ok>")
    assert env["RESULT"] == "it worked!"


def test_interpreters_run_func_rejects_interpreted_function_with_args():
    pytest.importorskip("_interpreters")
    source = """
from test.support import import_helper

_interpreters = import_helper.import_module("_interpreters")
interp = _interpreters.create()

def script(arg):
    return arg

try:
    _interpreters.run_func(interp, script)
except Exception as exc:
    RESULT = (type(exc).__name__, str(exc))
finally:
    _interpreters.destroy(interp)
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "__main__",
        "__package__": None,
        "__file__": "<interpreters_run_func_args>",
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename="<interpreters_run_func_args>")
    assert env["RESULT"][0] == "ValueError"


@pytest.mark.skipif(not HAS_TEMPLATE_STR, reason="TemplateStr requires Python 3.14+")
def test_templatestr_builds_template_with_interpolation_metadata(run_interpreter):
    source = """
name = "Bob"
width = 5
RESULT = t"hello {name!r:{width}}!"
"""
    env = run_interpreter(source)
    template = env["RESULT"]
    assert isinstance(template, templatelib.Template)
    assert template.strings == ("hello ", "!")
    assert template.values == ("Bob",)
    assert len(template.interpolations) == 1
    interpolation = template.interpolations[0]
    assert isinstance(interpolation, templatelib.Interpolation)
    assert interpolation.value == "Bob"
    assert interpolation.expression == "name"
    assert interpolation.conversion == "r"
    assert interpolation.format_spec == "5"


@pytest.mark.skipif(not HAS_TEMPLATE_STR, reason="TemplateStr requires Python 3.14+")
def test_templatestr_works_in_generator_execution_path(run_interpreter):
    source = """
def run():
    value = 42
    yield t"{value=}"

RESULT = list(run())
"""
    env = run_interpreter(source)
    [template] = env["RESULT"]
    assert isinstance(template, templatelib.Template)
    assert template.strings == ("value=", "")
    assert template.values == (42,)
    [interpolation] = template.interpolations
    assert interpolation.expression == "value"
    assert interpolation.conversion == "r"
    assert interpolation.format_spec == ""


@pytest.mark.skipif(not HAS_TEMPLATE_STR, reason="TemplateStr requires Python 3.14+")
def test_template_constructor_positional_call_without_empty_kwargs(run_interpreter):
    source = """
from string.templatelib import Template, Interpolation
RESULT = Template(Interpolation("Maria", "name", None, ""))
"""
    env = run_interpreter(source)
    template = env["RESULT"]
    assert isinstance(template, templatelib.Template)
    assert template.strings == ("", "")
    assert template.values == ("Maria",)


def test_from_import_relative_without_module_name_level_one(monkeypatch, tmp_path):
    package = tmp_path / "pkg_relimport_level_one"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "helper.py").write_text("VALUE = 42\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    source = """
from . import helper
from .helper import VALUE as COPIED
RESULT = (helper.VALUE, COPIED)
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "pkg_relimport_level_one.consumer",
        "__package__": "pkg_relimport_level_one",
        "__file__": str(package / "consumer.py"),
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename=str(package / "consumer.py"))

    assert env["RESULT"] == (42, 42)


def test_from_import_relative_without_module_name_level_two(monkeypatch, tmp_path):
    package = tmp_path / "pkg_relimport_level_two"
    subpackage = package / "subpkg"
    package.mkdir()
    subpackage.mkdir()
    (package / "__init__.py").write_text("")
    (subpackage / "__init__.py").write_text("")
    (package / "helper.py").write_text("FLAG = 'ok'\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    source = """
from .. import helper
RESULT = helper.FLAG
"""
    interpreter = Interpreter(allowed_imports=None, allow_relative_imports=True)
    env = {
        "__name__": "pkg_relimport_level_two.subpkg.consumer",
        "__package__": "pkg_relimport_level_two.subpkg",
        "__file__": str(subpackage / "consumer.py"),
        "__builtins__": dict(builtins.__dict__),
    }
    interpreter.run(source, env=env, filename=str(subpackage / "consumer.py"))

    assert env["RESULT"] == "ok"
