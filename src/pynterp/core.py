import ast
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterator, Optional, Set

from pynterp.lib import (
    InterpretedModuleLoader,
    import_safe_stdlib_module,
    make_safe_env,
)
from pynterp.lib.compat import maybe_patch_runtime_module

from .code import ModuleCode
from .scopes import ModuleScope, RuntimeScope


class InterpreterCore:
    def __init__(
        self, allowed_imports: Optional[Set[str]] = None, allow_relative_imports: bool = False
    ):
        """
        allowed_imports:
          - None  -> allow any import (NOT secure)
          - set() -> block all imports
          - {"math", "json"} -> allow only these roots (and their submodules)
        """
        self.allowed_imports = None if allowed_imports is None else set(allowed_imports)
        self.allow_relative_imports = bool(allow_relative_imports)

    # ----- restricted import -----

    def _is_allowed_module(self, name: str) -> bool:
        if self.allowed_imports is None:
            return True
        if not name:
            return False
        for allowed in self.allowed_imports:
            if (
                name == allowed
                or name.startswith(allowed + ".")
                or name.split(".", 1)[0] == allowed
            ):
                return True
        return False

    def _restricted_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level and not self.allow_relative_imports:
            raise ImportError("relative imports are not supported by this interpreter")
        if not self._is_allowed_module(name):
            raise ImportError(f"import of '{name}' is not allowed")
        module = import_safe_stdlib_module(name)
        # Match __import__ behavior: without fromlist, return the top-level package.
        if not fromlist and "." in name:
            return self._adapt_runtime_value(import_safe_stdlib_module(name.split(".", 1)[0]))
        return self._adapt_runtime_value(module)

    def _adapt_runtime_value(self, value: Any) -> Any:
        return maybe_patch_runtime_module(value)

    def _import(self, name: str, scope: RuntimeScope, fromlist=(), level=0):
        imp = scope.builtins.get("__import__")
        if imp is None or not callable(imp):
            raise ImportError("__import__ is not available in this environment")
        value = imp(name, scope.globals, scope.globals, fromlist, level)
        return self._adapt_runtime_value(value)

    def make_default_env(
        self,
        env: Optional[dict] = None,
        *,
        name: str = "__main__",
        package_root: str | Path | None = None,
        package_name: str = "pynterp",
    ) -> dict:
        if env is None:
            base: Dict[str, Any] = {}
        elif isinstance(env, dict):
            base = dict(env)
        else:
            raise TypeError("env must be dict or None")

        loader: InterpretedModuleLoader | None = None
        importer = self._restricted_import
        if package_root is not None:
            loader = InterpretedModuleLoader(
                self,
                package_name=package_name,
                package_root=package_root,
                fallback_importer=self._restricted_import,
            )
            importer = loader.import_module

        out = make_safe_env(importer, env=base, name=name)
        if loader is not None:
            out.setdefault("__module_loader__", loader)
        return out

    # ----- run -----

    def run(self, source: str, env: dict, filename: str = "<pynterp>") -> dict:
        """
        Execute `source` in a fresh AST interpreter module environment.

        Returns the module globals dict.
        """
        if not isinstance(env, dict):
            raise TypeError("env must be dict")
        globals_dict = env

        raw_builtins = globals_dict.get("__builtins__", {})
        if raw_builtins is None:
            builtins_dict: Dict[str, Any] = {}
        elif isinstance(raw_builtins, dict):
            builtins_dict = raw_builtins
        elif isinstance(raw_builtins, ModuleType):
            builtins_dict = raw_builtins.__dict__
        else:
            raise TypeError("__builtins__ must be dict, module, or None")

        code = ModuleCode(source, filename)
        scope = ModuleScope(code, globals_dict, builtins_dict)

        self.exec_module(code.tree, scope)
        return globals_dict

    # ----- dispatch (normal) -----

    def exec_module(self, node: ast.Module, scope: RuntimeScope) -> None:
        for stmt in node.body:
            self.exec_stmt(stmt, scope)

    def exec_block(self, stmts: list[ast.stmt], scope: RuntimeScope) -> None:
        for stmt in stmts:
            self.exec_stmt(stmt, scope)

    def exec_stmt(self, node: ast.AST, scope: RuntimeScope) -> None:
        m = getattr(self, f"exec_{node.__class__.__name__}", None)
        if m is None:
            raise NotImplementedError(f"Statement not supported: {node.__class__.__name__}")
        m(node, scope)

    def eval_expr(self, node: ast.AST, scope: RuntimeScope) -> Any:
        m = getattr(self, f"eval_{node.__class__.__name__}", None)
        if m is None:
            raise NotImplementedError(f"Expression not supported: {node.__class__.__name__}")
        return m(node, scope)

    # ----- dispatch (generator-mode) -----
    # These are Python generators so that `yield` in interpreted code maps to real Python yield.

    def g_exec_block(self, stmts: list[ast.stmt], scope: RuntimeScope) -> Iterator[Any]:
        for stmt in stmts:
            yield from self.g_exec_stmt(stmt, scope)

    def g_exec_stmt(self, node: ast.AST, scope: RuntimeScope) -> Iterator[Any]:
        m = getattr(self, f"g_exec_{node.__class__.__name__}", None)
        if m is None:
            # fallback: run a non-yielding statement
            self.exec_stmt(node, scope)
            return
        yield from m(node, scope)
        if False:
            yield None  # keeps it a generator in all branches

    def g_eval_expr(self, node: ast.AST, scope: RuntimeScope) -> Iterator[Any]:
        m = getattr(self, f"g_eval_{node.__class__.__name__}", None)
        if m is None:
            return self.eval_expr(node, scope)
        val = yield from m(node, scope)
        return val
