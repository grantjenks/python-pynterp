from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from .builtins import make_bootstrap_builtins


class InterpretedModuleLoader:
    """Import hook that executes package modules through an Interpreter instance."""

    def __init__(
        self,
        interpreter: Any,
        *,
        package_name: str,
        package_root: str | Path,
        fallback_importer: Callable[..., Any],
    ):
        self.interpreter = interpreter
        self.package_name = package_name
        self.package_root = Path(package_root)
        self.fallback_importer = fallback_importer

        self.modules: dict[str, ModuleType] = {}
        self.builtins = make_bootstrap_builtins(self.import_module)

    def import_module(self, name, globals=None, locals=None, fromlist=(), level=0):
        absolute_name = self._resolve_absolute_name(name, globals, level)

        if self._is_package_module(absolute_name):
            module = self._load_module(absolute_name)
        else:
            module = self.fallback_importer(absolute_name, globals, locals, fromlist, 0)

        fromlist = tuple(fromlist or ())
        if fromlist:
            for item in fromlist:
                if item == "*":
                    continue
                child_name = f"{absolute_name}.{item}"
                if (
                    self._is_package_module(child_name)
                    and self._module_path(child_name) is not None
                ):
                    child = self._load_module(child_name)
                    setattr(module, item, child)
            return module

        top_level = absolute_name.split(".", 1)[0]
        if top_level == self.package_name:
            return self._load_module(self.package_name)
        return module

    def _resolve_absolute_name(self, name: str, globals: dict | None, level: int) -> str:
        if level == 0:
            return name

        if not globals:
            raise ImportError("relative import requires package context")

        package = globals.get("__package__")
        if not package:
            module_name = globals.get("__name__", "")
            if globals.get("__path__") is not None:
                package = module_name
            else:
                package = module_name.rpartition(".")[0]

        if not package:
            raise ImportError("relative import requires package context")

        package_parts = package.split(".")
        if level > len(package_parts):
            raise ImportError("attempted relative import beyond top-level package")

        base = ".".join(package_parts[: len(package_parts) - level + 1])
        if not name:
            return base
        return f"{base}.{name}"

    def _is_package_module(self, name: str) -> bool:
        return name == self.package_name or name.startswith(f"{self.package_name}.")

    def _module_path(self, module_name: str) -> Path | None:
        if module_name == self.package_name:
            package_init = self.package_root / "__init__.py"
            return package_init if package_init.exists() else None

        relative = module_name[len(self.package_name) + 1 :].replace(".", "/")
        module_file = self.package_root / f"{relative}.py"
        if module_file.exists():
            return module_file

        package_init = self.package_root / relative / "__init__.py"
        if package_init.exists():
            return package_init

        return None

    def _load_module(self, module_name: str) -> ModuleType:
        existing = self.modules.get(module_name)
        if existing is not None:
            return existing

        module_path = self._module_path(module_name)
        if module_path is None:
            raise ImportError(f"module '{module_name}' not found in interpreted package")

        module = ModuleType(module_name)
        module_dict = module.__dict__
        module_dict["__name__"] = module_name
        module_dict["__file__"] = str(module_path)
        module_dict["__builtins__"] = self.builtins

        if module_path.name == "__init__.py":
            module_dict["__package__"] = module_name
            module_dict["__path__"] = [str(module_path.parent)]
        else:
            module_dict["__package__"] = module_name.rpartition(".")[0]

        self.modules[module_name] = module

        try:
            source = module_path.read_text()
            self.interpreter.run(source, env=module_dict, filename=str(module_path))
        except Exception:
            self.modules.pop(module_name, None)
            raise

        parent_name, _, child_name = module_name.rpartition(".")
        if parent_name:
            parent = self.modules.get(parent_name)
            if parent is not None:
                setattr(parent, child_name, module)

        return module
