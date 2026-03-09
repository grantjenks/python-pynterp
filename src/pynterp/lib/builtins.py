import builtins
import inspect
import sys
from typing import Any, Callable

from .guards import safe_delattr, safe_getattr, safe_hasattr, safe_setattr, safe_vars

_COMMON_BUILTIN_NAMES = (
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "BaseException",
    "BaseExceptionGroup",
    "BlockingIOError",
    "BrokenPipeError",
    "BufferError",
    "BytesWarning",
    "ChildProcessError",
    "ConnectionAbortedError",
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "DeprecationWarning",
    "EOFError",
    "Ellipsis",
    "Exception",
    "ExceptionGroup",
    "FileExistsError",
    "FileNotFoundError",
    "FloatingPointError",
    "FutureWarning",
    "GeneratorExit",
    "ImportError",
    "ImportWarning",
    "IndentationError",
    "IndexError",
    "InterruptedError",
    "IsADirectoryError",
    "KeyError",
    "LookupError",
    "MemoryError",
    "ModuleNotFoundError",
    "NameError",
    "NotADirectoryError",
    "NotImplemented",
    "NotImplementedError",
    "OSError",
    "OverflowError",
    "PendingDeprecationWarning",
    "PermissionError",
    "ProcessLookupError",
    "RecursionError",
    "ReferenceError",
    "ResourceWarning",
    "RuntimeError",
    "RuntimeWarning",
    "StopAsyncIteration",
    "StopIteration",
    "SyntaxError",
    "SyntaxWarning",
    "SystemError",
    "SystemExit",
    "TabError",
    "TimeoutError",
    "TypeError",
    "UnboundLocalError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "UnicodeError",
    "UnicodeTranslateError",
    "UnicodeWarning",
    "UserWarning",
    "ValueError",
    "Warning",
    "ZeroDivisionError",
    "abs",
    "aiter",
    "all",
    "anext",
    "any",
    "ascii",
    "bin",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "classmethod",
    "complex",
    "dict",
    "dir",
    "divmod",
    "enumerate",
    "exit",
    "filter",
    "float",
    "format",
    "frozenset",
    "globals",
    "hash",
    "hex",
    "id",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "locals",
    "map",
    "max",
    "memoryview",
    "min",
    "next",
    "object",
    "oct",
    "ord",
    "pow",
    "property",
    "print",
    "quit",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "super",
    "sum",
    "tuple",
    "type",
    "vars",
    "zip",
)


_USE_FUNCTION_SIGNATURE = object()


class SafeExposedCallableBase:
    __slots__ = ("__weakref__",)


def wrap_safe_callable(
    name: str,
    func: Callable[..., Any],
    *,
    qualname: str | None = None,
    doc: str | None = None,
    module: str | None = None,
    signature: inspect.Signature | None | object = _USE_FUNCTION_SIGNATURE,
    getitem: Callable[[Any], Any] | None = None,
) -> SafeExposedCallableBase:
    class SafeExposedCallable(SafeExposedCallableBase):
        __slots__ = ("__name__", "__qualname__", "__doc__", "__signature__")

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        def __getitem__(self, item: Any) -> Any:
            if getitem is None:
                raise TypeError(f"{type(self).__name__!r} object is not subscriptable")
            return getitem(item)

        def __setattr__(self, name: str, value: Any) -> None:
            raise AttributeError(f"{type(self).__name__!r} object is immutable")

        def __delattr__(self, name: str) -> None:
            raise AttributeError(f"{type(self).__name__!r} object is immutable")

    SafeExposedCallable.__module__ = getattr(func, "__module__", __name__) if module is None else module
    wrapped = SafeExposedCallable()
    object.__setattr__(wrapped, "__name__", name)
    object.__setattr__(wrapped, "__qualname__", qualname if qualname is not None else name)
    object.__setattr__(wrapped, "__doc__", getattr(func, "__doc__", None) if doc is None else doc)
    object.__setattr__(
        wrapped,
        "__signature__",
        inspect.signature(func) if signature is _USE_FUNCTION_SIGNATURE else signature,
    )
    return wrapped


SAFE_GETATTR = wrap_safe_callable("getattr", safe_getattr)
SAFE_HASATTR = wrap_safe_callable("hasattr", safe_hasattr)
SAFE_SETATTR = wrap_safe_callable("setattr", safe_setattr)
SAFE_DELATTR = wrap_safe_callable("delattr", safe_delattr)
SAFE_VARS = wrap_safe_callable("vars", safe_vars)


def is_safe_builtin_callable(value: Any, name: str | None = None) -> bool:
    if not isinstance(value, SafeExposedCallableBase):
        return False
    if name is None:
        return True
    return getattr(value, "__name__", None) == name


def _resolve_builtin(name: str) -> Any:
    value = getattr(builtins, name, None)
    if value is not None:
        return value
    if name in {"exit", "quit"}:
        return sys.exit
    raise AttributeError(f"module 'builtins' has no attribute {name!r}")


def make_safe_builtins(importer: Callable[..., Any]) -> dict[str, Any]:
    """Build builtins dictionary with guard-railed reflection helpers."""
    out = {name: _resolve_builtin(name) for name in _COMMON_BUILTIN_NAMES}
    out["getattr"] = SAFE_GETATTR
    out["hasattr"] = SAFE_HASATTR
    out["setattr"] = SAFE_SETATTR
    out["delattr"] = SAFE_DELATTR
    out["vars"] = SAFE_VARS
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
