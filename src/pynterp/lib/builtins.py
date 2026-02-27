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


def make_safe_builtins(importer: Callable[..., Any]) -> dict[str, Any]:
    """Build a small builtins dictionary suitable for the interpreter environment."""
    out = {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}
    out["__import__"] = importer
    return out


def make_safe_env(
    importer: Callable[..., Any], *, env: dict[str, Any] | None = None, name: str = "__main__"
) -> dict[str, Any]:
    """Create an explicit environment with safe defaults."""
    out: dict[str, Any] = {} if env is None else dict(env)
    out.setdefault("__builtins__", make_safe_builtins(importer))
    out.setdefault("__name__", name)
    return out
