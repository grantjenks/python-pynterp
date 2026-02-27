from __future__ import annotations

import functools
import inspect
import importlib
import sys
import types
from types import ModuleType
from typing import Any

_MISSING_SHARED = object()
_PY_CALLABLE = callable
_PY_GETATTR = getattr
_PY_ISINSTANCE = isinstance
_PY_ISSUBCLASS = issubclass


def _maybe_adapt_user_function_run_func_argument(func: Any, exc: TypeError) -> Any | None:
    if "argument 2 must be a function" not in str(exc):
        return None

    from pynterp.functions import UserFunction, adapt_user_function_for_interpreters_run_func

    if not _PY_ISINSTANCE(func, UserFunction):
        return None
    return adapt_user_function_for_interpreters_run_func(func)


def _patch_interpreters_run_func(module: ModuleType) -> None:
    original = _PY_GETATTR(module, "run_func", None)
    if not _PY_CALLABLE(original):
        return
    if _PY_GETATTR(original, "__pynterp_userfunction_adapter__", False):
        return

    def run_func_wrapper(interp: Any, func: Any, /, shared: Any = _MISSING_SHARED):
        if shared is _MISSING_SHARED:
            try:
                return original(interp, func)
            except TypeError as exc:
                adapted = _maybe_adapt_user_function_run_func_argument(func, exc)
                if adapted is None:
                    raise
                return original(interp, adapted)

        try:
            return original(interp, func, shared=shared)
        except TypeError as exc:
            adapted = _maybe_adapt_user_function_run_func_argument(func, exc)
            if adapted is None:
                raise
            return original(interp, adapted, shared=shared)

    run_func_wrapper.__name__ = _PY_GETATTR(original, "__name__", "run_func")
    run_func_wrapper.__qualname__ = _PY_GETATTR(original, "__qualname__", "run_func")
    run_func_wrapper.__doc__ = _PY_GETATTR(original, "__doc__", None)
    setattr(run_func_wrapper, "__pynterp_userfunction_adapter__", True)
    setattr(module, "run_func", run_func_wrapper)


def _unwrap_function_candidate(func: Any) -> Any:
    try:
        candidate = inspect.unwrap(func)
    except Exception:
        candidate = func

    while _PY_ISINSTANCE(candidate, functools.partial):
        candidate = candidate.func
        try:
            candidate = inspect.unwrap(candidate)
        except Exception:
            pass

    if _PY_ISINSTANCE(candidate, functools.partialmethod):
        try:
            candidate = inspect.unwrap(candidate.func)
        except Exception:
            candidate = candidate.func

    return candidate


def _maybe_source_for_user_function(func: Any) -> tuple[str, int] | None:
    from pynterp.functions import UserFunction

    candidate = _unwrap_function_candidate(func)
    if not _PY_ISINSTANCE(candidate, UserFunction):
        return None

    filename = _PY_GETATTR(candidate.code, "filename", None)
    lineno = _PY_GETATTR(candidate.node, "lineno", None)
    if not _PY_ISINSTANCE(filename, str) or not _PY_ISINSTANCE(lineno, int):
        return None
    return (filename, lineno)


def _patch_asyncio_format_helpers_get_function_source(module: ModuleType) -> None:
    original = _PY_GETATTR(module, "_get_function_source", None)
    if not _PY_CALLABLE(original):
        return
    if _PY_GETATTR(original, "__pynterp_userfunction_source_adapter__", False):
        return

    def get_function_source_wrapper(func: Any):
        source = original(func)
        if source is not None:
            return source
        return _maybe_source_for_user_function(func)

    get_function_source_wrapper.__name__ = _PY_GETATTR(original, "__name__", "_get_function_source")
    get_function_source_wrapper.__qualname__ = _PY_GETATTR(
        original, "__qualname__", "_get_function_source"
    )
    get_function_source_wrapper.__doc__ = _PY_GETATTR(original, "__doc__", None)
    setattr(get_function_source_wrapper, "__pynterp_userfunction_source_adapter__", True)
    setattr(module, "_get_function_source", get_function_source_wrapper)


def _resolve_unittest_name_target(name: Any, module: Any) -> tuple[Any, Any, str] | None:
    if not _PY_ISINSTANCE(name, str) or not name or module is None:
        return None

    parts = name.split(".")
    if any(not part for part in parts):
        return None

    obj = module
    parent: Any | None = None
    for part in parts:
        try:
            parent, obj = obj, _PY_GETATTR(obj, part)
        except Exception:
            return None

    if parent is None:
        return None
    return parent, obj, parts[-1]


def _suite_for_user_function_test_method(loader: Any, name: Any, module: Any) -> Any | None:
    from pynterp.functions import UserFunction
    import unittest.case as unittest_case

    resolved = _resolve_unittest_name_target(name, module)
    if resolved is None:
        return None
    parent, obj, method_name = resolved

    if not _PY_ISINSTANCE(obj, UserFunction):
        return None
    if not _PY_ISINSTANCE(parent, type):
        return None
    if not _PY_ISSUBCLASS(parent, unittest_case.TestCase):
        return None

    try:
        instance = parent(method_name)
        bound = _PY_GETATTR(instance, method_name)
    except Exception:
        return None

    # Match unittest.loader behavior: static methods should fall through to
    # callable handling, while bound test methods become a one-item suite.
    if _PY_ISINSTANCE(bound, (types.FunctionType, UserFunction)):
        return None
    return loader.suiteClass([instance])


def _patch_unittest_loader_load_tests_from_name(module: ModuleType) -> None:
    test_loader = _PY_GETATTR(module, "TestLoader", None)
    if not _PY_ISINSTANCE(test_loader, type):
        return

    original = _PY_GETATTR(test_loader, "loadTestsFromName", None)
    if not _PY_CALLABLE(original):
        return
    if _PY_GETATTR(original, "__pynterp_userfunction_testmethod_adapter__", False):
        return

    def load_tests_from_name_wrapper(self: Any, name: str, module: Any = None):
        suite = _suite_for_user_function_test_method(self, name, module)
        if suite is not None:
            return suite
        return original(self, name, module)

    load_tests_from_name_wrapper.__name__ = _PY_GETATTR(original, "__name__", "loadTestsFromName")
    load_tests_from_name_wrapper.__qualname__ = _PY_GETATTR(
        original, "__qualname__", "loadTestsFromName"
    )
    load_tests_from_name_wrapper.__doc__ = _PY_GETATTR(original, "__doc__", None)
    setattr(load_tests_from_name_wrapper, "__pynterp_userfunction_testmethod_adapter__", True)
    setattr(test_loader, "loadTestsFromName", load_tests_from_name_wrapper)


def _sync_subinterpreter_sys_path(interp: Any) -> None:
    # Subinterpreters do not always inherit runtime sys.path updates (like
    # probe-added CPython Lib roots), which breaks unpickling globals.
    parent_sys_path = tuple(path for path in sys.path if _PY_ISINSTANCE(path, str))
    interp.prepare_main(__pynterp_parent_sys_path__=parent_sys_path)
    interp.exec(
        "import sys as _pynterp_sys\n"
        "_pynterp_sys.path[:] = list(__pynterp_parent_sys_path__)\n"
        "del __pynterp_parent_sys_path__\n"
        "del _pynterp_sys\n"
    )


def _serialize_user_function_target(func: Any) -> tuple[str, str] | None:
    from pynterp.functions import UserFunction

    if not _PY_ISINSTANCE(func, UserFunction):
        return None

    module_name = _PY_GETATTR(func, "__module__", None)
    qualname = _PY_GETATTR(func, "__qualname__", None)
    if not _PY_ISINSTANCE(module_name, str) or not _PY_ISINSTANCE(qualname, str):
        return None
    if "<locals>" in qualname:
        return None
    return module_name, qualname


def _call_user_function_by_global_name(
    module_name: str,
    qualname: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    from pynterp.functions import _load_user_function_global

    func = _load_user_function_global(module_name, qualname)
    return func(*args, **kwargs)


def _patch_concurrent_futures_interpreter_worker_context(module: ModuleType) -> None:
    worker_context = _PY_GETATTR(module, "WorkerContext", None)
    if not _PY_ISINSTANCE(worker_context, type):
        return

    prepare = _PY_GETATTR(worker_context, "prepare", None)
    if not _PY_CALLABLE(prepare):
        return
    if not _PY_GETATTR(prepare, "__pynterp_userfunction_task_adapter__", False):
        def prepare_wrapper(cls: Any, initializer: Any, initargs: Any):
            def resolve_task(fn: Any, args: Any, kwargs: Any):
                serialized = _serialize_user_function_target(fn)
                if serialized is not None:
                    module_name, qualname = serialized
                    fn = _call_user_function_by_global_name
                    args = (module_name, qualname, tuple(args), dict(kwargs))
                    kwargs = {}
                if _PY_ISINSTANCE(fn, str):
                    # Match CPython's current interpreter-pool policy.
                    raise TypeError("scripts not supported")
                return (fn, args, kwargs)

            if initializer is not None:
                try:
                    initdata = resolve_task(initializer, initargs, {})
                except ValueError:
                    if _PY_ISINSTANCE(initializer, str) and initargs:
                        raise ValueError(
                            f"an initializer script does not take args, got {initargs!r}"
                        )
                    raise
            else:
                initdata = None

            def create_context():
                return cls(initdata)

            return create_context, resolve_task

        prepare_wrapper.__name__ = _PY_GETATTR(prepare, "__name__", "prepare")
        prepare_wrapper.__qualname__ = _PY_GETATTR(prepare, "__qualname__", "prepare")
        prepare_wrapper.__doc__ = _PY_GETATTR(prepare, "__doc__", None)
        setattr(prepare_wrapper, "__pynterp_userfunction_task_adapter__", True)
        setattr(worker_context, "prepare", classmethod(prepare_wrapper))

    original_run = _PY_GETATTR(worker_context, "run", None)
    if not _PY_CALLABLE(original_run):
        return
    if _PY_GETATTR(original_run, "__pynterp_subinterp_syspath_adapter__", False):
        return

    def run_wrapper(self: Any, task: Any):
        interp = _PY_GETATTR(self, "interp", None)
        if interp is not None and not _PY_GETATTR(self, "__pynterp_sys_path_synced__", False):
            _sync_subinterpreter_sys_path(interp)
            setattr(self, "__pynterp_sys_path_synced__", True)
        return original_run(self, task)

    run_wrapper.__name__ = _PY_GETATTR(original_run, "__name__", "run")
    run_wrapper.__qualname__ = _PY_GETATTR(original_run, "__qualname__", "run")
    run_wrapper.__doc__ = _PY_GETATTR(original_run, "__doc__", None)
    setattr(run_wrapper, "__pynterp_subinterp_syspath_adapter__", True)
    setattr(worker_context, "run", run_wrapper)


def _patch_concurrent_futures_module(module: ModuleType) -> None:
    try:
        interpreter_mod = importlib.import_module("concurrent.futures.interpreter")
    except Exception:
        return
    if type(interpreter_mod) is ModuleType:
        _patch_concurrent_futures_interpreter_worker_context(interpreter_mod)


def _patch_concurrent_module(module: ModuleType) -> None:
    futures_mod = _PY_GETATTR(module, "futures", None)
    if type(futures_mod) is ModuleType:
        _patch_concurrent_futures_module(futures_mod)


def maybe_patch_runtime_module(value: Any) -> Any:
    # Avoid isinstance() for arbitrary call results: it can trigger user
    # __class__ descriptors and mask the original call behavior.
    if type(value) is not ModuleType:
        return value
    if value.__name__ == "_interpreters":
        _patch_interpreters_run_func(value)
    if value.__name__ == "asyncio.format_helpers":
        _patch_asyncio_format_helpers_get_function_source(value)
    if value.__name__ == "asyncio":
        format_helpers = _PY_GETATTR(value, "format_helpers", None)
        if type(format_helpers) is ModuleType:
            _patch_asyncio_format_helpers_get_function_source(format_helpers)
    if value.__name__ == "unittest.loader":
        _patch_unittest_loader_load_tests_from_name(value)
    if value.__name__ == "unittest":
        loader_module = _PY_GETATTR(value, "loader", None)
        if type(loader_module) is ModuleType:
            _patch_unittest_loader_load_tests_from_name(loader_module)
    if value.__name__ == "concurrent":
        _patch_concurrent_module(value)
    if value.__name__ == "concurrent.futures.interpreter":
        _patch_concurrent_futures_interpreter_worker_context(value)
    if value.__name__ == "concurrent.futures":
        _patch_concurrent_futures_module(value)
    if value.__name__.startswith("concurrent.futures."):
        _patch_concurrent_futures_module(importlib.import_module("concurrent.futures"))
    return value
