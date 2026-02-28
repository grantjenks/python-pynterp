from __future__ import annotations
import __future__

import ast
import builtins
import collections
import collections.abc
import copy
import functools
import importlib.metadata as importlib_metadata
import inspect
import math
import operator
import pathlib
import symtable
import sys
import types
import typing
import weakref
from types import ModuleType

try:
    import string.templatelib as string_templatelib
except ImportError:  # pragma: no cover - Python < 3.14
    string_templatelib = None


def _make_importlib_proxy() -> ModuleType:
    module = ModuleType("importlib")
    module.__package__ = "importlib"
    module.__all__ = ["metadata"]
    module.metadata = importlib_metadata
    return module


_IMPORTLIB_PROXY = _make_importlib_proxy()

SAFE_STDLIB_MODULES: dict[str, ModuleType] = {
    "__future__": __future__,
    "ast": ast,
    "builtins": builtins,
    "collections": collections,
    "collections.abc": collections.abc,
    "copy": copy,
    "functools": functools,
    "importlib": _IMPORTLIB_PROXY,
    "importlib.metadata": importlib_metadata,
    "inspect": inspect,
    "math": math,
    "operator": operator,
    "pathlib": pathlib,
    "sys": sys,
    "symtable": symtable,
    "types": types,
    "typing": typing,
    "weakref": weakref,
}

if string_templatelib is not None:
    SAFE_STDLIB_MODULES["string.templatelib"] = string_templatelib


def import_safe_stdlib_module(name: str) -> ModuleType:
    """Load a module from the limited stdlib registry."""
    module = SAFE_STDLIB_MODULES.get(name)
    if module is None:
        raise ImportError(f"module '{name}' is not available in the safe stdlib")
    return module
