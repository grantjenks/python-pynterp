from __future__ import annotations

import functools
import inspect
from types import ModuleType
from typing import Any

_MISSING_SHARED = object()


def _maybe_adapt_user_function_run_func_argument(func: Any, exc: TypeError) -> Any | None:
    if "argument 2 must be a function" not in str(exc):
        return None

    from pynterp.functions import UserFunction, adapt_user_function_for_interpreters_run_func

    if not isinstance(func, UserFunction):
        return None
    return adapt_user_function_for_interpreters_run_func(func)


def _patch_interpreters_run_func(module: ModuleType) -> None:
    original = getattr(module, "run_func", None)
    if not callable(original):
        return
    if getattr(original, "__pynterp_userfunction_adapter__", False):
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

    run_func_wrapper.__name__ = getattr(original, "__name__", "run_func")
    run_func_wrapper.__qualname__ = getattr(original, "__qualname__", "run_func")
    run_func_wrapper.__doc__ = getattr(original, "__doc__", None)
    setattr(run_func_wrapper, "__pynterp_userfunction_adapter__", True)
    setattr(module, "run_func", run_func_wrapper)


def _unwrap_function_candidate(func: Any) -> Any:
    try:
        candidate = inspect.unwrap(func)
    except Exception:
        candidate = func

    while isinstance(candidate, functools.partial):
        candidate = candidate.func
        try:
            candidate = inspect.unwrap(candidate)
        except Exception:
            pass

    if isinstance(candidate, functools.partialmethod):
        try:
            candidate = inspect.unwrap(candidate.func)
        except Exception:
            candidate = candidate.func

    return candidate


def _maybe_source_for_user_function(func: Any) -> tuple[str, int] | None:
    from pynterp.functions import UserFunction

    candidate = _unwrap_function_candidate(func)
    if not isinstance(candidate, UserFunction):
        return None

    filename = getattr(candidate.code, "filename", None)
    lineno = getattr(candidate.node, "lineno", None)
    if not isinstance(filename, str) or not isinstance(lineno, int):
        return None
    return (filename, lineno)


def _patch_asyncio_format_helpers_get_function_source(module: ModuleType) -> None:
    original = getattr(module, "_get_function_source", None)
    if not callable(original):
        return
    if getattr(original, "__pynterp_userfunction_source_adapter__", False):
        return

    def get_function_source_wrapper(func: Any):
        source = original(func)
        if source is not None:
            return source
        return _maybe_source_for_user_function(func)

    get_function_source_wrapper.__name__ = getattr(original, "__name__", "_get_function_source")
    get_function_source_wrapper.__qualname__ = getattr(
        original, "__qualname__", "_get_function_source"
    )
    get_function_source_wrapper.__doc__ = getattr(original, "__doc__", None)
    setattr(get_function_source_wrapper, "__pynterp_userfunction_source_adapter__", True)
    setattr(module, "_get_function_source", get_function_source_wrapper)


def maybe_patch_runtime_module(value: Any) -> Any:
    if not isinstance(value, ModuleType):
        return value
    if value.__name__ == "_interpreters":
        _patch_interpreters_run_func(value)
    if value.__name__ == "asyncio.format_helpers":
        _patch_asyncio_format_helpers_get_function_source(value)
    if value.__name__ == "asyncio":
        format_helpers = getattr(value, "format_helpers", None)
        if isinstance(format_helpers, ModuleType):
            _patch_asyncio_format_helpers_get_function_source(format_helpers)
    return value
