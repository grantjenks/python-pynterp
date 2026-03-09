from __future__ import annotations

import builtins
import weakref
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .builtins import SafeExposedCallableBase, wrap_safe_callable

_LOCAL_MODULE_PROXY_ATTRS = frozenset(
    {
        "__all__",
        "__class__",
        "__delattr__",
        "__dir__",
        "__doc__",
        "__getattribute__",
        "__name__",
        "__package__",
        "__repr__",
        "__setattr__",
        "__slots__",
        "__str__",
        "__weakref__",
    }
)

_HIDDEN_OBJECT_PROXY_ATTRS = frozenset(
    {
        "_SafeObjectProxy__membrane",
        "_SafeObjectProxy__raw",
    }
)

_HIDDEN_TYPE_PROXY_ATTRS = frozenset(
    {
        "_SafeTypeProxy__membrane",
        "_SafeTypeProxy__raw",
        "_SafeTypeProxy__subclassable",
    }
)

_LOCAL_OBJECT_PROXY_ATTRS = frozenset(
    {
        "__class__",
        "__bool__",
        "__contains__",
        "__delattr__",
        "__delitem__",
        "__dict__",
        "__dir__",
        "__enter__",
        "__eq__",
        "__exit__",
        "__fspath__",
        "__ge__",
        "__getattribute__",
        "__getitem__",
        "__gt__",
        "__hash__",
        "__iter__",
        "__le__",
        "__len__",
        "__lt__",
        "__module__",
        "__ne__",
        "__next__",
        "__repr__",
        "__setattr__",
        "__setitem__",
        "__str__",
        "__truediv__",
        "__rtruediv__",
    }
    | _HIDDEN_OBJECT_PROXY_ATTRS
)

_LOCAL_TYPE_PROXY_ATTRS = frozenset(
    {
        "__call__",
        "__delattr__",
        "__dir__",
        "__eq__",
        "__ge__",
        "__getattribute__",
        "__getitem__",
        "__gt__",
        "__hash__",
        "__le__",
        "__lt__",
        "__mro_entries__",
        "__module__",
        "__ne__",
        "__or__",
        "__repr__",
        "__ror__",
        "__setattr__",
        "__str__",
    }
    | _HIDDEN_TYPE_PROXY_ATTRS
)


@dataclass(slots=True)
class _ModuleProxyState:
    raw: ModuleType
    membrane: "HostMembrane"


@dataclass(frozen=True, slots=True)
class ExposedHostClass:
    raw: type[Any]
    subclassable: bool = False


def expose_class(cls: type[Any], *, subclassable: bool = False) -> ExposedHostClass:
    if not isinstance(cls, type):
        raise TypeError("expose_class() expected a class object")
    return ExposedHostClass(raw=cls, subclassable=subclassable)


_MODULE_PROXY_STATES: "weakref.WeakKeyDictionary[SafeModuleProxy, _ModuleProxyState]" = (
    weakref.WeakKeyDictionary()
)


class SafeModuleProxy:
    __slots__ = ("__weakref__", "__name__", "__doc__", "__package__", "__all__")

    @property
    def __class__(self) -> type[ModuleType]:
        return type(_MODULE_PROXY_STATES[self].raw)

    def __getattribute__(self, name: str) -> Any:
        if name in _LOCAL_MODULE_PROXY_ATTRS:
            return object.__getattribute__(self, name)
        state = _MODULE_PROXY_STATES[self]
        return state.membrane.expose_external_value(getattr(state.raw, name), wrap_types=True)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"{type(self).__name__!r} object is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__!r} object is immutable")

    def __repr__(self) -> str:
        return repr(_MODULE_PROXY_STATES[self].raw)

    def __str__(self) -> str:
        return str(_MODULE_PROXY_STATES[self].raw)

    def __dir__(self) -> list[str]:
        state = _MODULE_PROXY_STATES[self]
        raw_names = set(dir(state.raw))
        raw_names.update({"__all__", "__doc__", "__name__", "__package__"})
        return sorted(raw_names)


def _object_proxy_raw(proxy: "SafeObjectProxy") -> Any:
    return object.__getattribute__(proxy, "_SafeObjectProxy__raw")


def _object_proxy_membrane(proxy: "SafeObjectProxy") -> "HostMembrane":
    return object.__getattribute__(proxy, "_SafeObjectProxy__membrane")


def _type_proxy_raw(proxy: "SafeTypeProxy") -> type[Any]:
    return object.__getattribute__(proxy, "_SafeTypeProxy__raw")


def _type_proxy_membrane(proxy: "SafeTypeProxy") -> "HostMembrane":
    return object.__getattribute__(proxy, "_SafeTypeProxy__membrane")


def _type_proxy_subclassable(proxy: "SafeTypeProxy") -> bool:
    return object.__getattribute__(proxy, "_SafeTypeProxy__subclassable")


class SafeObjectProxy:
    __slots__ = ("__weakref__", "__raw", "__membrane")

    @property
    def __class__(self) -> type[Any]:
        return type(_object_proxy_raw(self))

    @property
    def __module__(self) -> str | None:
        return getattr(_object_proxy_raw(self), "__module__", None)

    @property
    def __dict__(self) -> dict[str, Any]:
        raw_dict = getattr(_object_proxy_raw(self), "__dict__", None)
        if raw_dict is None:
            raise AttributeError(f"{type(self).__name__!r} object has no attribute '__dict__'")
        membrane = _object_proxy_membrane(self)
        return {
            key: membrane.expose_external_value(value, wrap_types=True)
            for key, value in raw_dict.items()
        }

    def __getattribute__(self, name: str) -> Any:
        if name in _HIDDEN_OBJECT_PROXY_ATTRS:
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
        if name in _LOCAL_OBJECT_PROXY_ATTRS:
            return object.__getattribute__(self, name)
        membrane = _object_proxy_membrane(self)
        return membrane.expose_external_value(
            getattr(_object_proxy_raw(self), name), wrap_types=True
        )

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _LOCAL_OBJECT_PROXY_ATTRS or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(f"{type(self).__name__!r} object is immutable")
        membrane = _object_proxy_membrane(self)
        setattr(_object_proxy_raw(self), name, membrane.unwrap_external_value(value))

    def __delattr__(self, name: str) -> None:
        if name in _LOCAL_OBJECT_PROXY_ATTRS or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(f"{type(self).__name__!r} object is immutable")
        delattr(_object_proxy_raw(self), name)

    def __repr__(self) -> str:
        return repr(_object_proxy_raw(self))

    def __str__(self) -> str:
        return str(_object_proxy_raw(self))

    def __dir__(self) -> list[str]:
        return sorted(set(dir(_object_proxy_raw(self))))

    def __bool__(self) -> bool:
        return bool(_object_proxy_raw(self))

    def __len__(self) -> int:
        return len(_object_proxy_raw(self))

    def __contains__(self, item: Any) -> bool:
        membrane = _object_proxy_membrane(self)
        return membrane.unwrap_external_value(item) in _object_proxy_raw(self)

    def __getitem__(self, item: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        raw_item = membrane.unwrap_external_value(item)
        return membrane.expose_external_value(_object_proxy_raw(self)[raw_item], wrap_types=True)

    def __setitem__(self, item: Any, value: Any) -> None:
        membrane = _object_proxy_membrane(self)
        raw_item = membrane.unwrap_external_value(item)
        raw_value = membrane.unwrap_external_value(value)
        _object_proxy_raw(self)[raw_item] = raw_value

    def __delitem__(self, item: Any) -> None:
        membrane = _object_proxy_membrane(self)
        raw_item = membrane.unwrap_external_value(item)
        del _object_proxy_raw(self)[raw_item]

    def __iter__(self) -> Any:
        raw_iter = iter(_object_proxy_raw(self))
        if raw_iter is _object_proxy_raw(self):
            return self
        return _object_proxy_membrane(self).expose_external_value(raw_iter, wrap_types=True)

    def __next__(self) -> Any:
        return _object_proxy_membrane(self).expose_external_value(
            next(_object_proxy_raw(self)),
            wrap_types=True,
        )

    def __enter__(self) -> Any:
        membrane = _object_proxy_membrane(self)
        return membrane.expose_external_value(_object_proxy_raw(self).__enter__(), wrap_types=True)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        raw_args = membrane.unwrap_external_value((exc_type, exc, tb))
        return _object_proxy_raw(self).__exit__(*raw_args)

    def __fspath__(self) -> Any:
        return _object_proxy_raw(self).__fspath__()

    def __hash__(self) -> int:
        return hash(_object_proxy_raw(self))

    def __eq__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) == membrane.unwrap_external_value(other)

    def __ne__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) != membrane.unwrap_external_value(other)

    def __lt__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) < membrane.unwrap_external_value(other)

    def __le__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) <= membrane.unwrap_external_value(other)

    def __gt__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) > membrane.unwrap_external_value(other)

    def __ge__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        return _object_proxy_raw(self) >= membrane.unwrap_external_value(other)

    def __truediv__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        raw_other = membrane.unwrap_external_value(other)
        return membrane.expose_external_value(_object_proxy_raw(self) / raw_other, wrap_types=True)

    def __rtruediv__(self, other: Any) -> Any:
        membrane = _object_proxy_membrane(self)
        raw_other = membrane.unwrap_external_value(other)
        return membrane.expose_external_value(raw_other / _object_proxy_raw(self), wrap_types=True)


class SafeTypeProxy:
    __slots__ = ("__raw", "__membrane", "__subclassable")

    @property
    def __module__(self) -> str | None:
        return getattr(_type_proxy_raw(self), "__module__", None)

    def __getattribute__(self, name: str) -> Any:
        if name in _HIDDEN_TYPE_PROXY_ATTRS:
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
        if name in _LOCAL_TYPE_PROXY_ATTRS:
            return object.__getattribute__(self, name)
        membrane = _type_proxy_membrane(self)
        return membrane.expose_external_value(getattr(_type_proxy_raw(self), name), wrap_types=True)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        raw_args = membrane.unwrap_external_value(args)
        raw_kwargs = membrane.unwrap_external_value(kwargs)
        if raw_kwargs:
            result = _type_proxy_raw(self)(*raw_args, **raw_kwargs)
        else:
            result = _type_proxy_raw(self)(*raw_args)
        return membrane.expose_external_value(result, wrap_types=True)

    def __getitem__(self, item: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        raw_item = membrane.unwrap_external_value(item)
        return membrane.expose_external_value(_type_proxy_raw(self)[raw_item], wrap_types=True)

    def __mro_entries__(self, bases: tuple[Any, ...]) -> tuple[type[Any], ...]:
        if not _type_proxy_subclassable(self):
            raise TypeError(
                "host classes exposed through env are constructor-only; wrap explicitly with "
                "expose_class(..., subclassable=True) to allow subclassing"
            )
        return (_type_proxy_raw(self),)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"{type(self).__name__!r} object is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__!r} object is immutable")

    def __repr__(self) -> str:
        return repr(_type_proxy_raw(self))

    def __str__(self) -> str:
        return str(_type_proxy_raw(self))

    def __dir__(self) -> list[str]:
        return sorted(set(dir(_type_proxy_raw(self))))

    def __hash__(self) -> int:
        return hash(_type_proxy_raw(self))

    def __eq__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) == membrane.unwrap_external_value(other)

    def __ne__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) != membrane.unwrap_external_value(other)

    def __lt__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) < membrane.unwrap_external_value(other)

    def __le__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) <= membrane.unwrap_external_value(other)

    def __gt__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) > membrane.unwrap_external_value(other)

    def __ge__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return _type_proxy_raw(self) >= membrane.unwrap_external_value(other)

    def __or__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return membrane.expose_external_value(
            _type_proxy_raw(self) | membrane.unwrap_external_value(other),
            wrap_types=True,
        )

    def __ror__(self, other: Any) -> Any:
        membrane = _type_proxy_membrane(self)
        return membrane.expose_external_value(
            membrane.unwrap_external_value(other) | _type_proxy_raw(self),
            wrap_types=True,
        )


class HostMembrane:
    def __init__(self) -> None:
        self._callable_cache: dict[int, tuple[Any, SafeExposedCallableBase]] = {}
        self._callable_wrappers: "weakref.WeakKeyDictionary[SafeExposedCallableBase, Any]" = (
            weakref.WeakKeyDictionary()
        )
        self._module_cache: dict[int, tuple[ModuleType, SafeModuleProxy]] = {}
        self._object_cache: dict[int, tuple[Any, SafeObjectProxy]] = {}
        self._type_cache: dict[tuple[int, bool], tuple[type[Any], SafeTypeProxy]] = {}

    def expose_external_value(
        self,
        value: Any,
        *,
        memo: dict[int, Any] | None = None,
        wrap_types: bool = False,
        reject_raw_types: bool = False,
    ) -> Any:
        if isinstance(value, ExposedHostClass):
            return self._wrap_type(value.raw, subclassable=value.subclassable)

        if (
            reject_raw_types
            and isinstance(value, type)
            and not isinstance(
                value,
                SafeExposedCallableBase | SafeModuleProxy | SafeObjectProxy | SafeTypeProxy,
            )
            and not self._is_internal_interpreter_value(value)
        ):
            raise TypeError(
                "raw host classes are not allowed in safe env; wrap them with pynterp.expose_class(...)"
            )

        if (
            wrap_types
            and isinstance(value, type)
            and not self._is_internal_interpreter_value(value)
        ):
            return self._wrap_type(value, subclassable=True)

        if self._is_passthrough_value(value):
            return value

        if memo is None:
            memo = {}

        obj_id = id(value)
        cached = memo.get(obj_id)
        if cached is not None:
            return cached

        if type(value) is ModuleType:
            return self._wrap_module(value)

        if self._should_wrap_callable(value):
            return self._wrap_callable(value)

        if isinstance(value, list):
            out: list[Any] = []
            memo[obj_id] = out
            out.extend(
                self.expose_external_value(
                    item,
                    memo=memo,
                    wrap_types=wrap_types,
                    reject_raw_types=reject_raw_types,
                )
                for item in value
            )
            return out

        if isinstance(value, tuple):
            out: list[Any] = []
            memo[obj_id] = out
            result = tuple(
                self.expose_external_value(
                    item,
                    memo=memo,
                    wrap_types=wrap_types,
                    reject_raw_types=reject_raw_types,
                )
                for item in value
            )
            memo[obj_id] = result
            return result

        if isinstance(value, set):
            out: set[Any] = set()
            memo[obj_id] = out
            for item in value:
                out.add(
                    self.expose_external_value(
                        item,
                        memo=memo,
                        wrap_types=wrap_types,
                        reject_raw_types=reject_raw_types,
                    )
                )
            return out

        if isinstance(value, frozenset):
            out: set[Any] = set()
            memo[obj_id] = out
            result = frozenset(
                self.expose_external_value(
                    item,
                    memo=memo,
                    wrap_types=wrap_types,
                    reject_raw_types=reject_raw_types,
                )
                for item in value
            )
            memo[obj_id] = result
            return result

        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            memo[obj_id] = out
            for key, item in value.items():
                out[
                    self.expose_external_value(
                        key,
                        memo=memo,
                        wrap_types=wrap_types,
                        reject_raw_types=reject_raw_types,
                    )
                ] = self.expose_external_value(
                    item,
                    memo=memo,
                    wrap_types=wrap_types,
                    reject_raw_types=reject_raw_types,
                )
            return out

        return self._wrap_object(value)

    def adapt_env_in_place(self, env: dict[str, Any]) -> None:
        for key, value in tuple(env.items()):
            if key == "__builtins__":
                continue
            env[key] = self.expose_external_value(value, reject_raw_types=True)

    def unwrap_external_value(self, value: Any, *, memo: dict[int, Any] | None = None) -> Any:
        if memo is None:
            memo = {}

        obj_id = id(value)
        cached = memo.get(obj_id)
        if cached is not None:
            return cached

        raw_callable = (
            self._callable_wrappers.get(value)
            if isinstance(value, SafeExposedCallableBase)
            else None
        )
        if raw_callable is not None:
            return raw_callable

        if isinstance(value, SafeModuleProxy):
            return _MODULE_PROXY_STATES[value].raw

        if isinstance(value, SafeObjectProxy):
            return _object_proxy_raw(value)

        if isinstance(value, SafeTypeProxy):
            return _type_proxy_raw(value)

        if isinstance(value, list):
            out: list[Any] = []
            memo[obj_id] = out
            out.extend(self.unwrap_external_value(item, memo=memo) for item in value)
            return out

        if isinstance(value, tuple):
            out: list[Any] = []
            memo[obj_id] = out
            result = tuple(self.unwrap_external_value(item, memo=memo) for item in value)
            memo[obj_id] = result
            return result

        if isinstance(value, set):
            out: set[Any] = set()
            memo[obj_id] = out
            for item in value:
                out.add(self.unwrap_external_value(item, memo=memo))
            return out

        if isinstance(value, frozenset):
            out: set[Any] = set()
            memo[obj_id] = out
            result = frozenset(self.unwrap_external_value(item, memo=memo) for item in value)
            memo[obj_id] = result
            return result

        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            memo[obj_id] = out
            for key, item in value.items():
                out[self.unwrap_external_value(key, memo=memo)] = self.unwrap_external_value(
                    item,
                    memo=memo,
                )
            return out

        return value

    def safe_type(self, *args: Any) -> Any:
        if len(args) == 1:
            return builtins.type(self.unwrap_external_value(args[0]))
        return builtins.type(*args)

    def safe_isinstance(self, obj: Any, class_or_tuple: Any) -> bool:
        return builtins.isinstance(
            self.unwrap_external_value(obj),
            self._unwrap_type_spec(class_or_tuple),
        )

    def safe_issubclass(self, cls: Any, class_or_tuple: Any) -> bool:
        return builtins.issubclass(
            self._unwrap_type_spec(cls),
            self._unwrap_type_spec(class_or_tuple),
        )

    def _wrap_callable(self, value: Any) -> SafeExposedCallableBase:
        cached_entry = self._callable_cache.get(id(value))
        if cached_entry is not None:
            cached_raw, cached_wrapper = cached_entry
            if cached_raw is value:
                return cached_wrapper

        def invoke(*args: Any, **kwargs: Any) -> Any:
            raw_args = self.unwrap_external_value(args)
            raw_kwargs = self.unwrap_external_value(kwargs)
            if raw_kwargs:
                result = value(*raw_args, **raw_kwargs)
            else:
                result = value(*raw_args)
            return self.expose_external_value(result, wrap_types=True)

        getitem = None
        if hasattr(value, "__getitem__"):

            def call_getitem(item: Any) -> Any:
                raw_item = self.unwrap_external_value(item)
                return self.expose_external_value(value[raw_item], wrap_types=True)

            getitem = call_getitem

        wrapper = wrap_safe_callable(
            getattr(value, "__name__", type(value).__name__),
            invoke,
            qualname=getattr(
                value, "__qualname__", getattr(value, "__name__", type(value).__name__)
            ),
            doc=getattr(value, "__doc__", None),
            module=getattr(value, "__module__", None),
            signature=None,
            getitem=getitem,
        )
        self._callable_cache[id(value)] = (value, wrapper)
        self._callable_wrappers[wrapper] = value
        return wrapper

    def _wrap_module(self, value: ModuleType) -> SafeModuleProxy:
        cached_entry = self._module_cache.get(id(value))
        if cached_entry is not None:
            cached_raw, cached_wrapper = cached_entry
            if cached_raw is value:
                return cached_wrapper

        wrapper = SafeModuleProxy()
        object.__setattr__(wrapper, "__name__", getattr(value, "__name__", "module"))
        object.__setattr__(wrapper, "__doc__", getattr(value, "__doc__", None))
        object.__setattr__(wrapper, "__package__", getattr(value, "__package__", None))
        names = getattr(value, "__all__", None)
        if names is None:
            names = tuple(
                name for name in getattr(value, "__dict__", {}).keys() if not name.startswith("_")
            )
        else:
            names = tuple(names)
        object.__setattr__(wrapper, "__all__", names)
        _MODULE_PROXY_STATES[wrapper] = _ModuleProxyState(raw=value, membrane=self)
        self._module_cache[id(value)] = (value, wrapper)
        return wrapper

    def _wrap_object(self, value: Any) -> SafeObjectProxy:
        cached_entry = self._object_cache.get(id(value))
        if cached_entry is not None:
            cached_raw, cached_wrapper = cached_entry
            if cached_raw is value:
                return cached_wrapper

        wrapper = SafeObjectProxy()
        object.__setattr__(wrapper, "_SafeObjectProxy__raw", value)
        object.__setattr__(wrapper, "_SafeObjectProxy__membrane", self)
        self._object_cache[id(value)] = (value, wrapper)
        return wrapper

    def _wrap_type(self, value: type[Any], *, subclassable: bool) -> SafeTypeProxy:
        cache_key = (id(value), subclassable)
        cached_entry = self._type_cache.get(cache_key)
        if cached_entry is not None:
            cached_raw, cached_wrapper = cached_entry
            if cached_raw is value:
                return cached_wrapper

        wrapper = SafeTypeProxy()
        object.__setattr__(wrapper, "_SafeTypeProxy__raw", value)
        object.__setattr__(wrapper, "_SafeTypeProxy__membrane", self)
        object.__setattr__(wrapper, "_SafeTypeProxy__subclassable", subclassable)
        self._type_cache[cache_key] = (value, wrapper)
        return wrapper

    def _is_passthrough_value(self, value: Any) -> bool:
        if value is None or isinstance(value, (bool, int, float, complex, str, bytes, bytearray)):
            return True
        if isinstance(value, (classmethod, staticmethod, property)):
            return True
        if isinstance(value, BaseException):
            return True
        if isinstance(
            value, SafeExposedCallableBase | SafeModuleProxy | SafeObjectProxy | SafeTypeProxy
        ):
            return True
        if isinstance(value, type):
            return True
        return self._is_internal_interpreter_value(value)

    def _should_wrap_callable(self, value: Any) -> bool:
        return callable(value) and not isinstance(value, type)

    def _unwrap_type_spec(self, value: Any) -> Any:
        if isinstance(value, tuple):
            return tuple(self._unwrap_type_spec(item) for item in value)
        return self.unwrap_external_value(value)

    def _is_internal_interpreter_value(self, value: Any) -> bool:
        try:
            from ..functions import BoundMethod, UserFunction
        except ImportError:  # pragma: no cover - defensive fallback
            return False
        return isinstance(value, (BoundMethod, UserFunction))
