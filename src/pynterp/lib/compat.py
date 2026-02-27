from __future__ import annotations

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


def maybe_patch_runtime_module(value: Any) -> Any:
    if not isinstance(value, ModuleType):
        return value
    if value.__name__ == "_interpreters":
        _patch_interpreters_run_func(value)
    return value
