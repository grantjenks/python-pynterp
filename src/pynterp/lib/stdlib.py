from __future__ import annotations
import __future__

import ast
import builtins
import math
import pathlib
import symtable
import types
import typing
from types import ModuleType

SAFE_STDLIB_MODULES: dict[str, ModuleType] = {
    "__future__": __future__,
    "ast": ast,
    "builtins": builtins,
    "math": math,
    "pathlib": pathlib,
    "symtable": symtable,
    "types": types,
    "typing": typing,
}


def import_safe_stdlib_module(name: str) -> ModuleType:
    """Load a module from the limited stdlib registry."""
    module = SAFE_STDLIB_MODULES.get(name)
    if module is None:
        raise ImportError(f"module '{name}' is not available in the safe stdlib")
    return module
