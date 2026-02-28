from __future__ import annotations

import inspect
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
        "__spec__",
        "__delattr__",
        "__subclasses__",
        "f_builtins",
        "f_globals",
        "f_locals",
        "gi_frame",
    }
)

_MISSING = object()


def _normalize_attr_name(name: Any) -> str:
    if not isinstance(name, str):
        raise TypeError("attribute name must be str")
    if type(name) is str:
        return name
    # Collapse str subclasses to a plain str so hash/eq overrides cannot
    # influence blocked-name checks or runtime attribute resolution.
    return str(name)


class _CodeMetadataAlias:
    __slots__ = ("co_name", "co_qualname", "co_filename", "co_firstlineno")

    def __init__(self, *, name: str, qualname: str, filename: str, firstlineno: int) -> None:
        self.co_name = name
        self.co_qualname = qualname
        self.co_filename = filename
        self.co_firstlineno = firstlineno


def _interpreted_async_generator_ag_code_alias(obj: Any) -> Any:
    gi_code = getattr(obj, "gi_code", _MISSING)
    if gi_code is _MISSING or getattr(gi_code, "co_name", None) != "async_gen_runner":
        return _MISSING

    gi_frame = getattr(obj, "gi_frame", _MISSING)
    if gi_frame is _MISSING or gi_frame is None:
        return _MISSING

    frame_locals = getattr(gi_frame, "f_locals", _MISSING)
    if not isinstance(frame_locals, dict):
        return _MISSING

    node = frame_locals.get("node")
    call_scope = frame_locals.get("call_scope")

    name = getattr(node, "name", None)
    qualname = getattr(call_scope, "qualname", None)
    if not isinstance(name, str) or not name:
        return _MISSING
    if not isinstance(qualname, str) or not qualname:
        qualname = name

    filename = getattr(gi_code, "co_filename", "<pynterp>")
    if not isinstance(filename, str):
        filename = "<pynterp>"

    firstlineno = getattr(gi_code, "co_firstlineno", 0)
    try:
        firstlineno = int(firstlineno)
    except (TypeError, ValueError):
        firstlineno = 0
    if firstlineno < 0:
        firstlineno = 0

    return _CodeMetadataAlias(
        name=name,
        qualname=qualname,
        filename=filename,
        firstlineno=firstlineno,
    )


def is_blocked_attr(name: str) -> bool:
    return name in _BLOCKED_ATTR_NAMES


def guard_attr_name(name: Any) -> str:
    normalized_name = _normalize_attr_name(name)
    if is_blocked_attr(normalized_name):
        raise AttributeError(
            f"attribute access to {normalized_name!r} is blocked in this environment"
        )
    return normalized_name


def safe_getattr(obj: Any, name: str, *default: Any) -> Any:
    name = _normalize_attr_name(name)
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
                attr_name = guard_attr_name(attr_name)

            if use_object_fallback and target is not _MISSING and attr_name is not _MISSING:
                resolved = inspect.getattr_static(target, attr_name)
                descriptor_get = getattr(type(resolved), "__get__", None)
                if descriptor_get is None:
                    return resolved
                return descriptor_get(resolved, target, type(target))

            return raw_getattribute(*args, **kwargs)

        return guarded_getattribute

    if name == "ag_code":
        alias = _interpreted_async_generator_ag_code_alias(obj)
        if alias is not _MISSING:
            return alias
        generic_generator_code = getattr(obj, "gi_code", _MISSING)
        if generic_generator_code is not _MISSING:
            return generic_generator_code

    name = guard_attr_name(name)
    if default:
        return getattr(obj, name, *default)
    return getattr(obj, name)


def safe_hasattr(obj: Any, name: str) -> bool:
    name = guard_attr_name(name)
    return hasattr(obj, name)


def safe_setattr(obj: Any, name: str, value: Any) -> None:
    name = guard_attr_name(name)
    setattr(obj, name, value)


def safe_delattr(obj: Any, name: str) -> None:
    name = guard_attr_name(name)
    delattr(obj, name)
