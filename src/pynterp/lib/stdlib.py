from __future__ import annotations

import math
from types import ModuleType

SAFE_STDLIB_MODULES: dict[str, ModuleType] = {
    "math": math,
}


def import_safe_stdlib_module(name: str) -> ModuleType:
    """Load a module from the limited stdlib registry."""
    module = SAFE_STDLIB_MODULES.get(name)
    if module is None:
        raise ImportError(f"module '{name}' is not available in the safe stdlib")
    return module
