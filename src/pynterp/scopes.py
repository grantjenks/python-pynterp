from __future__ import annotations

from typing import Any, Dict, MutableMapping, Set

from .code import ModuleCode, ScopeInfo
from .common import UNBOUND, Cell

_MISSING = object()


class RuntimeScope:
    def __init__(
        self,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        *,
        private_owner: str | None = None,
    ):
        self.code = code
        self.globals = globals_dict
        self.builtins = builtins_dict
        self.active_exception: BaseException | None = None
        self.private_owner = private_owner

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
        *,
        qualname: str | None = None,
        private_owner: str | None = None,
    ):
        super().__init__(
            code,
            globals_dict,
            builtins_dict,
            private_owner=private_owner,
        )
        self.scope_info = scope_info
        self.closure = dict(closure)
        self.qualname = qualname

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
                # Avoid isinstance() here: user-defined __getattribute__ on
                # interpreted objects can recurse when Python probes __class__.
                if type(val) is Cell:
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
        class_ns: MutableMapping[str, Any],
        class_cell: Cell | None = None,
        type_param_cells: Dict[str, Cell] | None = None,
        private_owner: str | None = None,
    ):
        super().__init__(
            code,
            globals_dict,
            builtins_dict,
            private_owner=private_owner,
        )
        self.outer_scope = outer_scope
        self.class_ns = class_ns
        self.class_cell = class_cell
        self.type_param_cells = dict(type_param_cells or {})
        self._shadowed_type_param_names: Set[str] = set()

    def _load_type_param(self, name: str, *, honor_shadowing: bool) -> Any:
        if honor_shadowing and name in self._shadowed_type_param_names:
            return _MISSING
        type_param_cell = self.type_param_cells.get(name)
        if type_param_cell is None:
            return _MISSING
        if type_param_cell.value is UNBOUND:
            raise NameError(name)
        return type_param_cell.value

    def _load_from_enclosing(self, name: str) -> Any:
        value = self._load_type_param(name, honor_shadowing=False)
        if value is not _MISSING:
            return value
        if isinstance(self.outer_scope, ClassBodyScope):
            return self.outer_scope._load_from_enclosing(name)
        return self.outer_scope.load(name)

    def load(self, name: str) -> Any:
        if name in self.class_ns:
            return self.class_ns[name]
        value = self._load_type_param(name, honor_shadowing=True)
        if value is not _MISSING:
            return value
        if isinstance(self.outer_scope, ClassBodyScope):
            return self.outer_scope._load_from_enclosing(name)
        return self.outer_scope.load(name)

    def store(self, name: str, value: Any) -> Any:
        self.class_ns[name] = value
        if name in self.type_param_cells:
            # Class-local rebinding shadows generic type params for direct loads
            # in the class body, but closures still capture the type-param cell.
            self._shadowed_type_param_names.add(name)
        return value

    def unbind(self, name: str) -> None:
        if name in self.class_ns:
            del self.class_ns[name]

    def delete(self, name: str) -> None:
        if name in self.class_ns:
            del self.class_ns[name]
            return
        raise NameError(name)

    def capture_cell(self, name: str) -> Cell:
        if name == "__class__" and self.class_cell is not None:
            return self.class_cell
        type_param_cell = self.type_param_cells.get(name)
        if type_param_cell is not None:
            return type_param_cell
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
        super().__init__(
            code,
            globals_dict,
            builtins_dict,
            private_owner=getattr(outer_scope, "private_owner", None),
        )
        self.outer_scope = outer_scope
        self.local_names = set(local_names)
        self.locals: Dict[str, Any] = {}
        self.cells: Dict[str, Cell] = {}

    def load(self, name: str) -> Any:
        if name in self.locals:
            val = self.locals[name]
            if type(val) is Cell:
                if val.value is UNBOUND:
                    raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
                return val.value
            if val is UNBOUND:
                raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
            return val
        if name in self.local_names:
            raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
        return self.outer_scope.load(name)

    def store(self, name: str, value: Any) -> Any:
        existing = self.locals.get(name, _MISSING)
        if type(existing) is Cell:
            existing.value = value
            return value
        self.locals[name] = value
        return value

    def unbind(self, name: str) -> None:
        existing = self.locals.get(name, _MISSING)
        if type(existing) is Cell:
            existing.value = UNBOUND
            return
        self.locals.pop(name, None)

    def delete(self, name: str) -> None:
        if name in self.locals:
            existing = self.locals[name]
            if type(existing) is Cell:
                if existing.value is UNBOUND:
                    raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
                existing.value = UNBOUND
            else:
                del self.locals[name]
            return
        if name in self.local_names:
            raise UnboundLocalError(f"local variable '{name}' referenced before assignment")
        self.outer_scope.delete(name)

    def capture_cell(self, name: str) -> Cell:
        if name in self.local_names:
            existing = self.locals.get(name, _MISSING)
            if type(existing) is Cell:
                return existing

            cell = Cell(UNBOUND if existing is _MISSING else existing)
            self.locals[name] = cell
            self.cells[name] = cell
            return cell
        return self.outer_scope.capture_cell(name)
