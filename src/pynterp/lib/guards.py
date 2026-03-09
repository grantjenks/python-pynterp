from __future__ import annotations

import builtins
import inspect
import types
import weakref
from types import ModuleType
from typing import Any

# Runtime internals and reflective dunders below are common pivot points for
# sandbox escapes (e.g. recovering globals/builtins/importers).
_BLOCKED_ATTR_NAMES = frozenset(
    {
        "__base__",
        "__bases__",
        "__builtins__",
        "__call__",
        "__closure__",
        "__code__",
        "__dict__",
        "__func__",
        "__getattr__",
        "__getattribute__",
        "__getnewargs__",
        "__getnewargs_ex__",
        "__getstate__",
        "__globals__",
        "__import__",
        "__loader__",
        "__mro__",
        "__reduce__",
        "__reduce_ex__",
        "__self__",
        "__setattr__",
        "__setstate__",
        "__spec__",
        "ag_code",
        "ag_frame",
        "cr_code",
        "cr_frame",
        "__delattr__",
        "__subclasses__",
        "f_back",
        "f_builtins",
        "f_code",
        "f_globals",
        "f_locals",
        "gi_code",
        "gi_frame",
        "tb_frame",
        "tb_next",
    }
)

_MISSING = object()
_RUNTIME_OWNED_OBJECTS: weakref.WeakSet[Any] = weakref.WeakSet()

_RUNTIME_INTERNAL_PRIVATE_ATTR_TYPES = frozenset(
    {
        ("pynterp.functions", "BoundMethod"),
        ("pynterp.functions", "UserFunction"),
        ("pynterp.helpers", "InterpretedAsyncGenerator"),
    }
)

_RUNTIME_INTERNAL_INSTANCE_ATTRS = {
    ("pynterp.functions", "BoundMethod"): frozenset(
        {
            "builtins",
            "closure",
            "code",
            "defaults",
            "globals",
            "is_async",
            "is_async_generator",
            "is_generator",
            "kw_defaults",
            "node",
            "scope_info",
        }
    ),
    ("pynterp.functions", "UserFunction"): frozenset(
        {
            "builtins",
            "closure",
            "code",
            "defaults",
            "globals",
            "is_async",
            "is_async_generator",
            "is_generator",
            "kw_defaults",
            "node",
            "scope_info",
        }
    ),
}

_RUNTIME_INTERNAL_CLASS_ATTRS = {
    ("pynterp.helpers", "InterpretedAsyncGenerator"): frozenset(
        {
            "_build_throw_exception",
            "_resume",
        }
    ),
}

_HOST_METADATA_MUTATION_ATTRS = frozenset(
    {
        "__annotations__",
        "__annotate__",
        "__signature__",
    }
)


def _normalize_attr_name(name: Any) -> str:
    if not isinstance(name, str):
        raise TypeError("attribute name must be str")
    if type(name) is str:
        return name
    # Collapse str subclasses to the base-string payload so str/hash/eq
    # overrides cannot influence blocked-name checks or runtime lookup.
    return str.__str__(name)


def is_blocked_attr(name: str) -> bool:
    return name in _BLOCKED_ATTR_NAMES


def mark_runtime_owned(obj: Any) -> Any:
    try:
        _RUNTIME_OWNED_OBJECTS.add(obj)
    except TypeError:
        pass
    return obj


def _is_runtime_owned(obj: Any) -> bool:
    try:
        return obj in _RUNTIME_OWNED_OBJECTS
    except TypeError:
        return False


def _allows_func_attr(obj: Any) -> bool:
    try:
        from ..functions import BoundMethod
    except ImportError:  # pragma: no cover - defensive fallback
        return False
    return isinstance(obj, BoundMethod)


def _runtime_type_key(obj: Any) -> tuple[str | None, str | None]:
    try:
        object.__getattribute__(obj, "__mro__")
    except AttributeError:
        cls = object.__getattribute__(obj, "__class__")
    else:
        cls = obj
    try:
        module = object.__getattribute__(cls, "__module__")
    except AttributeError:
        module = None
    try:
        name = object.__getattribute__(cls, "__name__")
    except AttributeError:
        name = None
    return module, name


def _blocks_runtime_internal_attr(obj: Any, name: str) -> bool:
    key = _runtime_type_key(obj)
    if (
        key in _RUNTIME_INTERNAL_PRIVATE_ATTR_TYPES
        and name.startswith("_")
        and not name.startswith("__")
    ):
        return True
    try:
        object.__getattribute__(obj, "__mro__")
    except AttributeError:
        is_type_object = False
    else:
        is_type_object = True
    if is_type_object:
        return name in _RUNTIME_INTERNAL_CLASS_ATTRS.get(key, ())
    return name in _RUNTIME_INTERNAL_INSTANCE_ATTRS.get(key, ())


def _guard_attr_name_for_object(obj: Any, name: Any) -> str:
    normalized_name = _normalize_attr_name(name)
    if normalized_name == "__func__" and _allows_func_attr(obj):
        return normalized_name
    if obj is not None and _blocks_runtime_internal_attr(obj, normalized_name):
        raise AttributeError(
            f"attribute access to {normalized_name!r} is blocked in this environment"
        )
    if is_blocked_attr(normalized_name):
        raise AttributeError(
            f"attribute access to {normalized_name!r} is blocked in this environment"
        )
    return normalized_name


def guard_attr_name(name: Any) -> str:
    return _guard_attr_name_for_object(None, name)


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
            call_args = args
            call_kwargs = kwargs
            attr_name = _MISSING
            name_kwarg_key = _MISSING

            for kwarg_key, kwarg_value in kwargs.items():
                if not isinstance(kwarg_key, str):
                    continue
                if _normalize_attr_name(kwarg_key) != "name":
                    continue
                if name_kwarg_key is not _MISSING:
                    raise TypeError(
                        "__getattribute__() got multiple values for keyword argument 'name'"
                    )
                name_kwarg_key = kwarg_key
                attr_name = kwarg_value

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
                attr_name = _guard_attr_name_for_object(
                    None if target is _MISSING else target, attr_name
                )
                if name_kwarg_key is not _MISSING:
                    call_kwargs = dict(kwargs)
                    if type(name_kwarg_key) is not str or name_kwarg_key != "name":
                        del call_kwargs[name_kwarg_key]
                    call_kwargs["name"] = attr_name
                elif raw_is_bound and args:
                    call_args = (attr_name,) + args[1:]
                elif not raw_is_bound and len(args) > 1:
                    call_args = (args[0], attr_name) + args[2:]

            if use_object_fallback and target is not _MISSING and attr_name is not _MISSING:
                resolved = inspect.getattr_static(target, attr_name)
                descriptor_get = getattr(type(resolved), "__get__", None)
                if descriptor_get is None:
                    return resolved
                return descriptor_get(resolved, target, type(target))

            return raw_getattribute(*call_args, **call_kwargs)

        return guarded_getattribute

    name = _guard_attr_name_for_object(obj, name)
    if default:
        return getattr(obj, name, *default)
    return getattr(obj, name)


def safe_hasattr(obj: Any, name: str) -> bool:
    name = _guard_attr_name_for_object(obj, name)
    return hasattr(obj, name)


def safe_vars(*args: Any) -> Any:
    if not args:
        return builtins.vars()
    mapping = builtins.vars(*args)
    if not hasattr(mapping, "items"):
        return mapping
    obj = args[0]
    return {
        key: value
        for key, value in mapping.items()
        if not isinstance(key, str)
        or (
            not is_blocked_attr(_normalize_attr_name(key))
            and not _blocks_runtime_internal_attr(obj, _normalize_attr_name(key))
        )
    }


def _guard_host_metadata_mutation(obj: Any, name: str) -> None:
    if name not in _HOST_METADATA_MUTATION_ATTRS:
        return
    if isinstance(obj, types.FunctionType | ModuleType):
        raise AttributeError(
            f"mutation of {name!r} on host runtime objects is blocked in this environment"
        )
    if isinstance(obj, type) and not _is_runtime_owned(obj):
        raise AttributeError(
            f"mutation of {name!r} on host runtime objects is blocked in this environment"
        )


def safe_setattr(obj: Any, name: str, value: Any) -> None:
    name = guard_attr_name(name)
    _guard_host_metadata_mutation(obj, name)
    setattr(obj, name, value)


def safe_delattr(obj: Any, name: str) -> None:
    name = guard_attr_name(name)
    _guard_host_metadata_mutation(obj, name)
    delattr(obj, name)
