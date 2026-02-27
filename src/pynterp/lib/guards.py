from __future__ import annotations

from typing import Any

# Runtime internals and reflective dunders below are common pivot points for
# sandbox escapes (e.g. recovering globals/builtins/importers).
_BLOCKED_ATTR_NAMES = frozenset(
    {
        "__base__",
        "__bases__",
        "__builtins__",
        "__closure__",
        "__code__",
        "__dict__",
        "__func__",
        "__getattr__",
        "__getattribute__",
        "__globals__",
        "__import__",
        "__loader__",
        "__mro__",
        "__reduce__",
        "__reduce_ex__",
        "__self__",
        "__setattr__",
        "__delattr__",
        "__spec__",
        "__subclasses__",
        "__traceback__",
        "f_back",
        "f_builtins",
        "f_globals",
        "f_locals",
        "gi_frame",
        "cr_frame",
        "ag_frame",
        "tb_frame",
        "tb_next",
    }
)


def is_blocked_attr(name: str) -> bool:
    return name in _BLOCKED_ATTR_NAMES


def guard_attr_name(name: str) -> None:
    if not isinstance(name, str):
        raise TypeError("attribute name must be str")
    if is_blocked_attr(name):
        raise AttributeError(f"attribute access to {name!r} is blocked in this environment")


def safe_getattr(obj: Any, name: str, *default: Any) -> Any:
    guard_attr_name(name)
    if default:
        return getattr(obj, name, *default)
    return getattr(obj, name)


def safe_hasattr(obj: Any, name: str) -> bool:
    guard_attr_name(name)
    return hasattr(obj, name)


def safe_setattr(obj: Any, name: str, value: Any) -> None:
    guard_attr_name(name)
    setattr(obj, name, value)


def safe_delattr(obj: Any, name: str) -> None:
    guard_attr_name(name)
    delattr(obj, name)
