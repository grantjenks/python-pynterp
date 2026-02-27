from __future__ import annotations

import inspect
from typing import Any

# Runtime internals and reflective dunders below are common pivot points for
# sandbox escapes (e.g. recovering globals/builtins/importers).
_BLOCKED_ATTR_NAMES = frozenset(
    {
        "__base__",
        "__builtins__",
        "__closure__",
        "__code__",
        "__dict__",
        "__getattr__",
        "__getattribute__",
        "__globals__",
        "__import__",
        "__mro__",
        "__reduce__",
        "__reduce_ex__",
        "__self__",
        "__setattr__",
        "__delattr__",
        "__subclasses__",
        "f_builtins",
        "f_globals",
        "f_locals",
        "gi_frame",
        "ag_frame",
        "tb_frame",
    }
)

_MISSING = object()


def is_blocked_attr(name: str) -> bool:
    return name in _BLOCKED_ATTR_NAMES


def guard_attr_name(name: str) -> None:
    if not isinstance(name, str):
        raise TypeError("attribute name must be str")
    if is_blocked_attr(name):
        raise AttributeError(f"attribute access to {name!r} is blocked in this environment")


def safe_getattr(obj: Any, name: str, *default: Any) -> Any:
    if name == "__getattribute__":
        try:
            raw_getattribute = getattr(obj, name)
        except AttributeError:
            if default:
                return default[0]
            raise

        raw_is_bound = getattr(raw_getattribute, "__self__", _MISSING) is not _MISSING
        raw_objclass = getattr(raw_getattribute, "__objclass__", None)
        use_object_fallback = raw_objclass is object and not raw_is_bound

        def guarded_getattribute(*args: Any, **kwargs: Any) -> Any:
            target = _MISSING
            attr_name = kwargs.get("name", _MISSING)
            if raw_is_bound:
                target = getattr(raw_getattribute, "__self__", _MISSING)
                if attr_name is _MISSING and args:
                    attr_name = args[0]
            else:
                if args:
                    target = args[0]
                if attr_name is _MISSING and len(args) > 1:
                    attr_name = args[1]

            if attr_name is not _MISSING:
                guard_attr_name(attr_name)

            if use_object_fallback and target is not _MISSING and attr_name is not _MISSING:
                resolved = inspect.getattr_static(target, attr_name)
                descriptor_get = getattr(type(resolved), "__get__", None)
                if descriptor_get is None:
                    return resolved
                return descriptor_get(resolved, target, type(target))

            return raw_getattribute(*args, **kwargs)

        return guarded_getattribute

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
