from __future__ import annotations

from typing import Any, Dict, Set

from .code import ModuleCode, ScopeInfo
from .common import UNBOUND, Cell


class RuntimeScope:
    def __init__(self, code: ModuleCode, globals_dict: dict, builtins_dict: dict):
        self.code = code
        self.globals = globals_dict
        self.builtins = builtins_dict

    def load(self, name: str) -> Any:
        raise NotImplementedError

    def store(self, name: str, value: Any) -> Any:
        raise NotImplementedError

    def unbind(self, name: str) -> None:
        """Forgiving delete used for internal cleanup (e.g. except name)."""
        raise NotImplementedError

    def delete(self, name: str) -> None:
        """Strict delete used for `del name`."""
        raise NotImplementedError

    def capture_cell(self, name: str) -> Cell:
        raise NotImplementedError


class ModuleScope(RuntimeScope):
    def load(self, name: str) -> Any:
        if name in self.globals:
            return self.globals[name]
        if name in self.builtins:
            return self.builtins[name]
        raise NameError(name)

    def store(self, name: str, value: Any) -> Any:
        self.globals[name] = value
        return value

    def unbind(self, name: str) -> None:
        self.globals.pop(name, None)

    def delete(self, name: str) -> None:
        if name in self.globals:
            del self.globals[name]
            return
        raise NameError(name)

    def capture_cell(self, name: str) -> Cell:
        raise NameError(f"cannot capture free variable {name!r} from module scope")


class FunctionScope(RuntimeScope):
    def __init__(
        self,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        scope_info: ScopeInfo,
        closure: Dict[str, Cell],
    ):
        super().__init__(code, globals_dict, builtins_dict)
        self.scope_info = scope_info
        self.closure = dict(closure)

        # locals maps name -> value OR Cell
        self.locals: Dict[str, Any] = {}
        self.cells: Dict[str, Cell] = {}

        # pre-create cells for cellvars
        for name in scope_info.cellvars:
            cell = Cell(UNBOUND)
            self.cells[name] = cell
            self.locals[name] = cell

    def load(self, name: str) -> Any:
        si = self.scope_info

        # Local (fast/local slot)
        if name in si.locals:
            if name in self.locals:
                val = self.locals[name]
                if isinstance(val, Cell):
                    if val.value is UNBOUND:
                        raise UnboundLocalError(
                            f"local variable '{name}' referenced before assignment"
                        )
                    return val.value
                return val
            raise UnboundLocalError(f"local variable '{name}' referenced before assignment")

        # Free var (closure)
        if name in si.frees:
            cell = self.closure.get(name)
            if cell is None:
                raise NameError(f"free variable '{name}' is not available in closure")
            if cell.value is UNBOUND:
                raise NameError(
                    f"cannot access free variable '{name}' where it is not associated "
                    f"with a value in enclosing scope"
                )
            return cell.value

        # Global / builtins
        if name in self.globals:
            return self.globals[name]
        if name in self.builtins:
            return self.builtins[name]
        raise NameError(name)

    def store(self, name: str, value: Any) -> Any:
        si = self.scope_info

        # global statement
        if name in si.declared_globals:
            self.globals[name] = value
            return value

        # nonlocal / free
        if name in si.frees:
            cell = self.closure.get(name)
            if cell is None:
                raise NameError(f"cannot assign to free variable '{name}' (missing closure cell)")
            cell.value = value
            return value

        # cellvar
        if name in si.cellvars:
            self.cells[name].value = value
            return value

        # regular local
        self.locals[name] = value
        return value

    def unbind(self, name: str) -> None:
        si = self.scope_info
        if name in si.declared_globals:
            self.globals.pop(name, None)
            return
        if name in si.frees:
            cell = self.closure.get(name)
            if cell is not None:
                cell.value = UNBOUND
            return
        if name in si.cellvars:
            self.cells[name].value = UNBOUND
            return
        self.locals.pop(name, None)

    def delete(self, name: str) -> None:
        si = self.scope_info

        if name in si.declared_globals:
            if name in self.globals:
                del self.globals[name]
                return
            raise NameError(name)

        if name in si.frees:
            cell = self.closure.get(name)
            if cell is None or cell.value is UNBOUND:
                raise NameError(name)
            cell.value = UNBOUND
            return

        # local
        if name in si.locals:
            if name in si.cellvars:
                if self.cells[name].value is UNBOUND:
                    raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
                self.cells[name].value = UNBOUND
                return
            if name not in self.locals:
                raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
            del self.locals[name]
            return

        # maybe global fallback
        if name in self.globals:
            del self.globals[name]
            return
        raise NameError(name)

    def capture_cell(self, name: str) -> Cell:
        si = self.scope_info
        if name in si.cellvars:
            return self.cells[name]
        if name in si.frees:
            cell = self.closure.get(name)
            if cell is None:
                raise NameError(f"free variable '{name}' is not available for capture")
            return cell
        raise NameError(f"cannot capture '{name}': not a cellvar or freevar in this scope")


class ClassBodyScope(RuntimeScope):
    """
    Executes a class body into `class_ns`.

    Important behavior:
      - loads: check class_ns first, else fall back to outer scope
      - stores: always into class_ns
      - closure capture for methods: delegated to OUTER scope (not class namespace)
        (matches CPython behavior: methods don't close over class locals)
    """

    def __init__(
        self,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        outer_scope: RuntimeScope,
        class_ns: Dict[str, Any],
    ):
        super().__init__(code, globals_dict, builtins_dict)
        self.outer_scope = outer_scope
        self.class_ns = class_ns

    def load(self, name: str) -> Any:
        if name in self.class_ns:
            return self.class_ns[name]
        return self.outer_scope.load(name)

    def store(self, name: str, value: Any) -> Any:
        self.class_ns[name] = value
        return value

    def unbind(self, name: str) -> None:
        self.class_ns.pop(name, None)

    def delete(self, name: str) -> None:
        if name in self.class_ns:
            del self.class_ns[name]
            return
        raise NameError(name)

    def capture_cell(self, name: str) -> Cell:
        return self.outer_scope.capture_cell(name)


class ComprehensionScope(RuntimeScope):
    """
    A small scope for list/set/dict comps and genexpr.

    We keep a local mapping for the comprehension's targets so they DON'T leak,
    while loads fall back to the outer scope.
    """

    def __init__(
        self,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        outer_scope: RuntimeScope,
        local_names: Set[str],
    ):
        super().__init__(code, globals_dict, builtins_dict)
        self.outer_scope = outer_scope
        self.local_names = set(local_names)
        self.locals: Dict[str, Any] = {}

    def load(self, name: str) -> Any:
        if name in self.locals:
            val = self.locals[name]
            if val is UNBOUND:
                raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
            return val
        if name in self.local_names:
            raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
        return self.outer_scope.load(name)

    def store(self, name: str, value: Any) -> Any:
        self.locals[name] = value
        return value

    def unbind(self, name: str) -> None:
        self.locals.pop(name, None)

    def delete(self, name: str) -> None:
        if name in self.locals:
            del self.locals[name]
            return
        if name in self.local_names:
            raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
        self.outer_scope.delete(name)

    def capture_cell(self, name: str) -> Cell:
        return self.outer_scope.capture_cell(name)
