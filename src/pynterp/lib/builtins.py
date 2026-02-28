import builtins
from typing import Any, Callable

from .guards import safe_delattr, safe_getattr, safe_hasattr, safe_setattr

_COMMON_BUILTIN_NAMES = (
    "BaseException",
    "BaseExceptionGroup",
    "Exception",
    "ExceptionGroup",
    "ImportError",
    "NameError",
    "NotImplementedError",
    "RuntimeError",
    "TypeError",
    "UnboundLocalError",
    "ValueError",
    "ZeroDivisionError",
    "abs",
    "all",
    "any",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "dict",
    "enumerate",
    "float",
    "frozenset",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "max",
    "min",
    "next",
    "object",
    "property",
    "print",
    "range",
    "reversed",
    "round",
    "set",
    "slice",
    "staticmethod",
    "str",
    "super",
    "sum",
    "tuple",
    "type",
    "zip",
)


def make_safe_builtins(importer: Callable[..., Any]) -> dict[str, Any]:
    """Build builtins dictionary with guard-railed reflection helpers."""
    out = {name: getattr(builtins, name) for name in _COMMON_BUILTIN_NAMES}
    out["getattr"] = safe_getattr
    out["hasattr"] = safe_hasattr
    out["setattr"] = safe_setattr
    out["delattr"] = safe_delattr
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
