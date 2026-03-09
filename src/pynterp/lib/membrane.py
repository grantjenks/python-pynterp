from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any
import weakref

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


@dataclass(slots=True)
class _ModuleProxyState:
    raw: ModuleType
    membrane: "HostMembrane"


_MODULE_PROXY_STATES: "weakref.WeakKeyDictionary[SafeModuleProxy, _ModuleProxyState]" = (
    weakref.WeakKeyDictionary()
)


class SafeModuleProxy:
    __slots__ = ("__weakref__", "__name__", "__doc__", "__package__", "__all__")

    def __getattribute__(self, name: str) -> Any:
        if name in _LOCAL_MODULE_PROXY_ATTRS:
            return object.__getattribute__(self, name)
        state = _MODULE_PROXY_STATES[self]
        return state.membrane.expose_external_value(getattr(state.raw, name))

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


class HostMembrane:
    def __init__(self) -> None:
        self._callable_cache: dict[int, tuple[Any, SafeExposedCallableBase]] = {}
        self._callable_wrappers: "weakref.WeakKeyDictionary[SafeExposedCallableBase, Any]" = (
            weakref.WeakKeyDictionary()
        )
        self._module_cache: dict[int, tuple[ModuleType, SafeModuleProxy]] = {}

    def expose_external_value(self, value: Any, *, memo: dict[int, Any] | None = None) -> Any:
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
            out.extend(self.expose_external_value(item, memo=memo) for item in value)
            return out

        if isinstance(value, tuple):
            out: list[Any] = []
            memo[obj_id] = out
            result = tuple(self.expose_external_value(item, memo=memo) for item in value)
            memo[obj_id] = result
            return result

        if isinstance(value, set):
            out: set[Any] = set()
            memo[obj_id] = out
            for item in value:
                out.add(self.expose_external_value(item, memo=memo))
            return out

        if isinstance(value, frozenset):
            out: set[Any] = set()
            memo[obj_id] = out
            result = frozenset(self.expose_external_value(item, memo=memo) for item in value)
            memo[obj_id] = result
            return result

        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            memo[obj_id] = out
            for key, item in value.items():
                out[self.expose_external_value(key, memo=memo)] = self.expose_external_value(
                    item,
                    memo=memo,
                )
            return out

        return value

    def adapt_env_in_place(self, env: dict[str, Any]) -> None:
        for key, value in tuple(env.items()):
            if key == "__builtins__":
                continue
            env[key] = self.expose_external_value(value)

    def unwrap_external_value(self, value: Any, *, memo: dict[int, Any] | None = None) -> Any:
        if memo is None:
            memo = {}

        obj_id = id(value)
        cached = memo.get(obj_id)
        if cached is not None:
            return cached

        raw_callable = self._callable_wrappers.get(value) if isinstance(value, SafeExposedCallableBase) else None
        if raw_callable is not None:
            return raw_callable

        if isinstance(value, SafeModuleProxy):
            return _MODULE_PROXY_STATES[value].raw

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

    def _wrap_callable(self, value: Any) -> SafeExposedCallableBase:
        cached_entry = self._callable_cache.get(id(value))
        if cached_entry is not None:
            cached_raw, cached_wrapper = cached_entry
            if cached_raw is value:
                return cached_wrapper

        def invoke(*args: Any, **kwargs: Any) -> Any:
            raw_args = self.unwrap_external_value(args)
            raw_kwargs = self.unwrap_external_value(kwargs)
            return self.expose_external_value(value(*raw_args, **raw_kwargs))

        getitem = None
        if hasattr(value, "__getitem__"):
            def call_getitem(item: Any) -> Any:
                raw_item = self.unwrap_external_value(item)
                return self.expose_external_value(value[raw_item])

            getitem = call_getitem

        wrapper = wrap_safe_callable(
            getattr(value, "__name__", type(value).__name__),
            invoke,
            qualname=getattr(value, "__qualname__", getattr(value, "__name__", type(value).__name__)),
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
            names = tuple(name for name in getattr(value, "__dict__", {}).keys() if not name.startswith("_"))
        else:
            names = tuple(names)
        object.__setattr__(wrapper, "__all__", names)
        _MODULE_PROXY_STATES[wrapper] = _ModuleProxyState(raw=value, membrane=self)
        self._module_cache[id(value)] = (value, wrapper)
        return wrapper

    def _is_passthrough_value(self, value: Any) -> bool:
        if value is None or isinstance(value, (bool, int, float, complex, str, bytes, bytearray)):
            return True
        if isinstance(value, SafeExposedCallableBase | SafeModuleProxy):
            return True
        if isinstance(value, type):
            return True
        return self._is_internal_interpreter_value(value)

    def _should_wrap_callable(self, value: Any) -> bool:
        return callable(value) and not isinstance(value, type)

    def _is_internal_interpreter_value(self, value: Any) -> bool:
        try:
            from ..functions import BoundMethod, UserFunction
        except ImportError:  # pragma: no cover - defensive fallback
            return False
        return isinstance(value, (BoundMethod, UserFunction))
