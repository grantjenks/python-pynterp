from __future__ import annotations

import builtins
from typing import Any, Callable

SAFE_BUILTIN_NAMES = (
    "BaseException",
    "Exception",
    "ImportError",
    "NameError",
    "RuntimeError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "print",
    "range",
    "round",
    "set",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
)

BOOTSTRAP_EXTRA_BUILTIN_NAMES = (
    "NotImplementedError",
    "UnboundLocalError",
    "all",
    "any",
    "callable",
    "delattr",
    "getattr",
    "hasattr",
    "isinstance",
    "issubclass",
    "iter",
    "next",
    "object",
    "reversed",
    "setattr",
    "slice",
    "super",
)


def make_safe_builtins(importer: Callable[..., Any]) -> dict[str, Any]:
    """Build a small builtins dictionary suitable for the interpreter environment."""
    out = {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}
    out["__import__"] = importer
    return out


def make_bootstrap_builtins(importer: Callable[..., Any]) -> dict[str, Any]:
    """Build a richer builtins dictionary for self-hosting interpreter bootstrap."""
    out = make_safe_builtins(importer)
    out.update({name: getattr(builtins, name) for name in BOOTSTRAP_EXTRA_BUILTIN_NAMES})
    return out


def make_safe_env(
    importer: Callable[..., Any], *, env: dict[str, Any] | None = None, name: str = "__main__"
) -> dict[str, Any]:
    """Create an explicit environment with safe defaults."""
    out: dict[str, Any] = {} if env is None else dict(env)
    out.setdefault("__builtins__", make_safe_builtins(importer))
    out.setdefault("__name__", name)
    return out


def make_bootstrap_env(
    importer: Callable[..., Any], *, env: dict[str, Any] | None = None, name: str = "__main__"
) -> dict[str, Any]:
    """Create an explicit environment for interpreter self-hosting bootstrap."""
    out: dict[str, Any] = {} if env is None else dict(env)
    out.setdefault("__builtins__", make_bootstrap_builtins(importer))
    out.setdefault("__name__", name)
    return out
