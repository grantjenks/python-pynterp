import builtins
import sys
from typing import Any, Callable

from .guards import safe_delattr, safe_getattr, safe_hasattr, safe_setattr

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
