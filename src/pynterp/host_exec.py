from __future__ import annotations

import builtins
from typing import Any


def prepare_host_globals(
    globals_dict: dict[str, Any], builtins_dict: dict[str, Any], *, copy: bool = False
) -> dict[str, Any]:
    """Ensure host eval/exec never sees a globals dict without safe builtins."""
    namespace = dict(globals_dict) if copy else globals_dict
    namespace.setdefault("__builtins__", builtins_dict)
    return namespace


def safe_host_eval(
    source: Any,
    globals_dict: dict[str, Any],
    builtins_dict: dict[str, Any],
    locals_dict: Any,
    *,
    copy_globals: bool = False,
) -> Any:
    return builtins.eval(
        source,
        prepare_host_globals(globals_dict, builtins_dict, copy=copy_globals),
        locals_dict,
    )


def safe_host_exec(
    source: Any,
    globals_dict: dict[str, Any],
    builtins_dict: dict[str, Any],
    locals_dict: Any | None = None,
    *,
    copy_globals: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    namespace = prepare_host_globals(globals_dict, builtins_dict, copy=copy_globals)
    builtins.exec(source, namespace, namespace if locals_dict is None else locals_dict, **kwargs)
    return namespace
