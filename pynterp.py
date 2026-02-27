"""pynterp.py

A small AST-walk interpreter that executes a meaningful Python subset
directly from `ast.parse`, with:

- proper-ish lexical scoping (closures, global, nonlocal) via `symtable`
- with-statement support
- import with a restricted import hook
- del statement
- class statement (minimal metaclass support)
- comprehensions: list/set/dict comprehensions + generator expressions
- yield / yield from (generator functions)

The goal is a secure sandbox with a lot of flexibility regarding what is
supported: open, object model introspection, etc.

Targeting Python 3.14 style AST (uses ast.Constant, symtable).
"""

from __future__ import annotations

import ast
import builtins
import symtable
from typing import Any, Dict, Iterable, Iterator, Optional, Set


UNBOUND = object()


# ----------------------------
# Control-flow signals (internal)
# ----------------------------

class ControlFlowSignal(BaseException):
    """Internal non-user exceptions used for control flow (return/break/continue)."""


class ReturnSignal(ControlFlowSignal):
    def __init__(self, value: Any):
        self.value = value


class BreakSignal(ControlFlowSignal):
    pass


class ContinueSignal(ControlFlowSignal):
    pass


class Cell:
    """A tiny closure cell."""
    __slots__ = ("value",)

    def __init__(self, value: Any = UNBOUND):
        self.value = value

    def __repr__(self) -> str:
        return "<Cell UNBOUND>" if self.value is UNBOUND else f"<Cell {self.value!r}>"


# ----------------------------
# symtable helpers
# ----------------------------

def _table_frees(table: symtable.SymbolTable) -> Set[str]:
    """
    Get "free variables" for any symtable block.

    - Function tables have `get_frees()`.
    - Class tables don't, but their Symbol objects can be marked free.
      (And importantly, class tables' frees include frees needed by methods.)
    """
    if hasattr(table, "get_frees"):
        return set(table.get_frees())
    return {s.get_name() for s in table.get_symbols() if s.is_free()}


def _contains_yield(fn_node: ast.FunctionDef) -> bool:
    """
    True iff this function's body contains Yield/YieldFrom (ignoring nested defs/classes/lambdas).
    """
    class Finder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Yield(self, node: ast.Yield) -> None:
            self.found = True

        def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
            self.found = True

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return  # don't descend

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

    finder = Finder()
    for stmt in fn_node.body:
        if finder.found:
            break
        finder.visit(stmt)
    return finder.found


def _collect_target_names(target: ast.AST) -> Set[str]:
    names: Set[str] = set()

    def rec(t: ast.AST) -> None:
        if isinstance(t, ast.Name):
            names.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                rec(e)
        elif isinstance(t, ast.Starred):
            rec(t.value)
        # ignore Attribute/Subscript/etc

    rec(target)
    return names


def _collect_comprehension_locals(gens: list[ast.comprehension]) -> Set[str]:
    out: Set[str] = set()
    for g in gens:
        out |= _collect_target_names(g.target)
    return out


# ----------------------------
# Code object wrapper (AST + symtable + cellvar analysis)
# ----------------------------

class ScopeInfo:
    """
    Per-function scope info needed for runtime name resolution.
    """
    def __init__(self, table: symtable.Function, cellvars: Set[str]):
        self.table = table
        self.locals: Set[str] = set(table.get_locals())
        self.frees: Set[str] = set(table.get_frees())
        self.cellvars: Set[str] = set(cellvars)
        self.declared_globals: Set[str] = {
            s.get_name() for s in table.get_symbols() if s.is_declared_global()
        }


class ModuleCode:
    """
    Holds:
      - parsed AST
      - symtable tree
      - a mapping from (type,name,lineno) -> table
      - computed cellvars for each function table
    """
    def __init__(self, source: str, filename: str = "<pynterp>"):
        self.source = source
        self.filename = filename
        self.tree = ast.parse(source, filename=filename, mode="exec")
        self.sym_root = symtable.symtable(source, filename, "exec")

        self._tables_by_key: Dict[tuple[str, str, int], list[symtable.SymbolTable]] = {}
        self._cellvars_by_id: Dict[int, Set[str]] = {}

        self._index_tables(self.sym_root)
        self._compute_cellvars(self.sym_root)

    def _index_tables(self, table: symtable.SymbolTable) -> None:
        key = (table.get_type(), table.get_name(), table.get_lineno())
        self._tables_by_key.setdefault(key, []).append(table)
        for child in table.get_children():
            self._index_tables(child)

    def _compute_cellvars(self, table: symtable.SymbolTable) -> None:
        for child in table.get_children():
            self._compute_cellvars(child)

        if table.get_type() == "function":
            assert isinstance(table, symtable.Function)
            locals_ = set(table.get_locals())
            child_frees: Set[str] = set()
            for child in table.get_children():
                child_frees |= _table_frees(child)
            self._cellvars_by_id[table.get_id()] = locals_ & child_frees
        else:
            self._cellvars_by_id[table.get_id()] = set()

    def lookup_function_table(self, fn_node: ast.FunctionDef) -> symtable.Function:
        key = ("function", fn_node.name, fn_node.lineno)
        tables = self._tables_by_key.get(key, [])
        if not tables:
            raise RuntimeError(
                f"Could not find symtable for function {fn_node.name!r} at line {fn_node.lineno}"
            )
        if len(tables) > 1:
            raise RuntimeError(
                f"Ambiguous symtable match for function {fn_node.name!r} at line {fn_node.lineno}"
            )
        tbl = tables[0]
        if not isinstance(tbl, symtable.Function):
            raise RuntimeError("lookup_function_table returned non-function table")
        return tbl

    def scope_info_for(self, fn_table: symtable.Function) -> ScopeInfo:
        return ScopeInfo(fn_table, self._cellvars_by_id.get(fn_table.get_id(), set()))


# ----------------------------
# Runtime scopes
# ----------------------------

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
                    raise UnboundLocalError(
                        f"local variable '{name}' referenced before assignment"
                    )
                self.cells[name].value = UNBOUND
                return
            if name not in self.locals:
                raise UnboundLocalError(
                    f"local variable '{name}' referenced before assignment"
                )
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
                raise UnboundLocalError(
                    f"local variable '{name}' referenced before assignment"
                )
            return val
        if name in self.local_names:
            raise UnboundLocalError(
                f"local variable '{name}' referenced before assignment"
            )
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
            raise UnboundLocalError(
                f"local variable '{name}' referenced before assignment"
            )
        self.outer_scope.delete(name)

    def capture_cell(self, name: str) -> Cell:
        return self.outer_scope.capture_cell(name)


# ----------------------------
# Function objects + binding in classes
# ----------------------------

class BoundMethod:
    def __init__(self, func: "UserFunction", self_obj: Any):
        self._func = func
        self._self = self_obj
        self.__name__ = getattr(func, "__name__", type(func).__name__)

    def __call__(self, *args, **kwargs):
        return self._func(self._self, *args, **kwargs)

    def __repr__(self) -> str:
        return f"<bound method {self._func!r} of {self._self!r}>"


class UserFunction:
    """
    A callable representing a user-defined function interpreted by Interpreter.

    Implements descriptor protocol so it behaves like a Python function when placed
    on a class (so __init__ gets self bound, methods bind self, etc).
    """
    def __init__(
        self,
        interpreter: "Interpreter",
        node: ast.FunctionDef,
        code: ModuleCode,
        globals_dict: dict,
        scope_info: ScopeInfo,
        closure: Dict[str, Cell],
        defaults: list[Any],
        kw_defaults: list[Any],
        is_generator: bool,
    ):
        self.interpreter = interpreter
        self.node = node
        self.code = code
        self.globals = globals_dict
        self.scope_info = scope_info
        self.closure = dict(closure)
        self.defaults = list(defaults)
        self.kw_defaults = list(kw_defaults)
        self.is_generator = is_generator
        self.__name__ = node.name
        self.__qualname__ = node.name

    def __repr__(self) -> str:
        kind = "gen" if self.is_generator else "func"
        return f"<UserFunction {self.__name__} ({kind})>"

    def __call__(self, *args, **kwargs):
        return self.interpreter._call_user_function(self, args, kwargs)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return BoundMethod(self, obj)


# ----------------------------
# The interpreter
# ----------------------------

class Interpreter:
    def __init__(self, allowed_imports: Optional[Set[str]] = None, allow_relative_imports: bool = False):
        """
        allowed_imports:
          - None  -> allow any import (NOT secure)
          - set() -> block all imports
          - {"math", "json"} -> allow only these roots (and their submodules)
        """
        self.allowed_imports = None if allowed_imports is None else set(allowed_imports)
        self.allow_relative_imports = bool(allow_relative_imports)

        self.builtins = dict(builtins.__dict__)
        self.builtins["__import__"] = self._restricted_import

    # ----- restricted import -----

    def _is_allowed_module(self, name: str) -> bool:
        if self.allowed_imports is None:
            return True
        if not name:
            return False
        for allowed in self.allowed_imports:
            if name == allowed or name.startswith(allowed + ".") or name.split(".", 1)[0] == allowed:
                return True
        return False

    def _restricted_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level and not self.allow_relative_imports:
            raise ImportError("relative imports are not supported by this interpreter")
        if not self._is_allowed_module(name):
            raise ImportError(f"import of '{name}' is not allowed")
        return builtins.__import__(name, globals, locals, fromlist, level)

    def _import(self, name: str, scope: RuntimeScope, fromlist=(), level=0):
        imp = self.builtins["__import__"]
        return imp(name, scope.globals, scope.globals, fromlist, level)

    # ----- run -----

    def run(self, source: str, env: Optional[dict] = None, filename: str = "<pynterp>") -> dict:
        """
        Execute `source` in a fresh AST interpreter module environment.

        Returns the module globals dict.
        """
        if env is None:
            globals_dict: Dict[str, Any] = {}
        elif isinstance(env, dict):
            globals_dict = env
        else:
            raise TypeError("env must be dict or None")

        globals_dict.setdefault("__builtins__", self.builtins)
        globals_dict.setdefault("__name__", "__main__")

        code = ModuleCode(source, filename)
        scope = ModuleScope(code, globals_dict, self.builtins)

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

    # ----------------------------
    # Statements (normal)
    # ----------------------------

    def exec_Expr(self, node: ast.Expr, scope: RuntimeScope) -> None:
        self.eval_expr(node.value, scope)

    def exec_Pass(self, node: ast.Pass, scope: RuntimeScope) -> None:
        return

    def exec_Assign(self, node: ast.Assign, scope: RuntimeScope) -> None:
        val = self.eval_expr(node.value, scope)
        for tgt in node.targets:
            self._assign_target(tgt, val, scope)

    def exec_AnnAssign(self, node: ast.AnnAssign, scope: RuntimeScope) -> None:
        # Minimal: evaluate annotation + (optional) value.
        if node.value is not None:
            val = self.eval_expr(node.value, scope)
            self._assign_target(node.target, val, scope)

        if isinstance(node.target, ast.Name):
            ann = self.eval_expr(node.annotation, scope)
            ns = scope.class_ns if isinstance(scope, ClassBodyScope) else scope.globals
            anns = ns.get("__annotations__")
            if anns is None:
                anns = {}
                ns["__annotations__"] = anns
            anns[node.target.id] = ann

    def exec_AugAssign(self, node: ast.AugAssign, scope: RuntimeScope) -> None:
        if not isinstance(node.target, ast.Name):
            raise NotImplementedError("AugAssign only supports Name targets here")
        name = node.target.id
        old = scope.load(name)
        rhs = self.eval_expr(node.value, scope)
        scope.store(name, self._apply_binop(node.op, old, rhs))

    def exec_If(self, node: ast.If, scope: RuntimeScope) -> None:
        if self.eval_expr(node.test, scope):
            self.exec_block(node.body, scope)
        else:
            self.exec_block(node.orelse, scope)

    def exec_While(self, node: ast.While, scope: RuntimeScope) -> None:
        broke = False
        while self.eval_expr(node.test, scope):
            try:
                self.exec_block(node.body, scope)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if (not broke) and node.orelse:
            self.exec_block(node.orelse, scope)

    def exec_For(self, node: ast.For, scope: RuntimeScope) -> None:
        it = self.eval_expr(node.iter, scope)
        broke = False
        for item in it:
            self._assign_target(node.target, item, scope)
            try:
                self.exec_block(node.body, scope)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if (not broke) and node.orelse:
            self.exec_block(node.orelse, scope)

    def exec_Break(self, node: ast.Break, scope: RuntimeScope) -> None:
        raise BreakSignal()

    def exec_Continue(self, node: ast.Continue, scope: RuntimeScope) -> None:
        raise ContinueSignal()

    def exec_Return(self, node: ast.Return, scope: RuntimeScope) -> None:
        val = self.eval_expr(node.value, scope) if node.value is not None else None
        raise ReturnSignal(val)

    def exec_Delete(self, node: ast.Delete, scope: RuntimeScope) -> None:
        for tgt in node.targets:
            self._delete_target(tgt, scope)

    def exec_Global(self, node: ast.Global, scope: RuntimeScope) -> None:
        # symtable drives the behavior; statement itself is a no-op at runtime
        return

    def exec_Nonlocal(self, node: ast.Nonlocal, scope: RuntimeScope) -> None:
        return

    def exec_FunctionDef(self, node: ast.FunctionDef, scope: RuntimeScope) -> None:
        defaults = [self.eval_expr(d, scope) for d in (node.args.defaults or [])]
        kw_defaults = [
            (self.eval_expr(d, scope) if d is not None else None)
            for d in (getattr(node.args, "kw_defaults", []) or [])
        ]

        fn_table = scope.code.lookup_function_table(node)
        fn_scope_info = scope.code.scope_info_for(fn_table)

        closure = {name: scope.capture_cell(name) for name in fn_scope_info.frees}
        is_gen = _contains_yield(node)

        func = UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            scope_info=fn_scope_info,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=is_gen,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = self.eval_expr(dec_node, scope)
            decorated = dec(decorated)

        scope.store(node.name, decorated)

    def exec_ClassDef(self, node: ast.ClassDef, scope: RuntimeScope) -> None:
        bases = [self.eval_expr(b, scope) for b in node.bases]
        kw: Dict[str, Any] = {}
        for k in node.keywords:
            if k.arg is None:
                kw.update(self.eval_expr(k.value, scope))
            else:
                kw[k.arg] = self.eval_expr(k.value, scope)

        meta = kw.pop("metaclass", None)
        if meta is None:
            meta = type(bases[0]) if bases else type

        class_ns: Dict[str, Any] = {}
        class_ns.setdefault("__module__", scope.globals.get("__name__", "__main__"))
        class_ns.setdefault("__qualname__", node.name)

        body_scope = ClassBodyScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, class_ns=class_ns
        )
        self.exec_block(node.body, body_scope)

        cls = meta(node.name, tuple(bases), class_ns, **kw)

        decorated: Any = cls
        for dec_node in reversed(node.decorator_list or []):
            dec = self.eval_expr(dec_node, scope)
            decorated = dec(decorated)

        scope.store(node.name, decorated)

    def exec_Try(self, node: ast.Try, scope: RuntimeScope) -> None:
        try:
            self.exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise
            handled = False
            for handler in node.handlers:
                if handler.type is None:
                    match = True
                else:
                    exc_type = self.eval_expr(handler.type, scope)
                    match = isinstance(e, exc_type)
                if match:
                    handled = True
                    if handler.name:
                        scope.store(handler.name, e)
                    try:
                        self.exec_block(handler.body, scope)
                    finally:
                        if handler.name:
                            scope.unbind(handler.name)
                    break
            if not handled:
                raise
        else:
            if node.orelse:
                self.exec_block(node.orelse, scope)
        finally:
            if node.finalbody:
                self.exec_block(node.finalbody, scope)

    def exec_Raise(self, node: ast.Raise, scope: RuntimeScope) -> None:
        if node.exc is None:
            raise RuntimeError("re-raise not supported in this interpreter")
        exc = self.eval_expr(node.exc, scope)
        if isinstance(exc, BaseException):
            raise exc
        if isinstance(exc, type) and issubclass(exc, BaseException):
            raise exc()
        raise TypeError("Can only raise exception instances or exception classes")

    def exec_With(self, node: ast.With, scope: RuntimeScope) -> None:
        exits = []
        try:
            for item in node.items:
                mgr = self.eval_expr(item.context_expr, scope)
                enter = getattr(mgr, "__enter__")
                exit_ = getattr(mgr, "__exit__")
                val = enter()
                exits.append(exit_)
                if item.optional_vars is not None:
                    self._assign_target(item.optional_vars, val, scope)

            self.exec_block(node.body, scope)

        except ControlFlowSignal:
            for exit_ in reversed(exits):
                exit_(None, None, None)
            raise

        except BaseException as e:
            exc_type = type(e)
            exc = e
            tb = e.__traceback__

            for exit_ in reversed(exits):
                try:
                    suppress = exit_(exc_type, exc, tb)
                except BaseException as new_e:
                    exc_type = type(new_e)
                    exc = new_e
                    tb = new_e.__traceback__
                    continue
                if suppress:
                    exc_type = exc = tb = None

            if exc_type is None:
                return
            raise exc

        else:
            for exit_ in reversed(exits):
                exit_(None, None, None)

    def exec_Import(self, node: ast.Import, scope: RuntimeScope) -> None:
        for alias in node.names:
            mod = self._import(alias.name, scope, fromlist=(), level=0)
            bind = alias.asname or alias.name.split(".", 1)[0]
            scope.store(bind, mod)

    def exec_ImportFrom(self, node: ast.ImportFrom, scope: RuntimeScope) -> None:
        if node.level and not self.allow_relative_imports:
            raise ImportError("relative imports are not supported by this interpreter")
        if node.module is None:
            raise ImportError("from-import without module not supported")
        fromlist = [a.name for a in node.names if a.name != "*"]
        mod = self._import(node.module, scope, fromlist=fromlist or ("*",), level=node.level or 0)

        for alias in node.names:
            if alias.name == "*":
                names = getattr(mod, "__all__", None)
                if names is None:
                    names = [k for k in getattr(mod, "__dict__", {}).keys() if not k.startswith("_")]
                for k in names:
                    scope.store(k, getattr(mod, k))
            else:
                scope.store(alias.asname or alias.name, getattr(mod, alias.name))

    # ----------------------------
    # Expressions (normal)
    # ----------------------------

    def eval_Constant(self, node: ast.Constant, scope: RuntimeScope) -> Any:
        return node.value

    def eval_Name(self, node: ast.Name, scope: RuntimeScope) -> Any:
        if isinstance(node.ctx, ast.Load):
            return scope.load(node.id)
        raise NotImplementedError("Name ctx other than Load not supported here")

    def eval_BinOp(self, node: ast.BinOp, scope: RuntimeScope) -> Any:
        left = self.eval_expr(node.left, scope)
        right = self.eval_expr(node.right, scope)
        return self._apply_binop(node.op, left, right)

    def eval_UnaryOp(self, node: ast.UnaryOp, scope: RuntimeScope) -> Any:
        operand = self.eval_expr(node.operand, scope)
        if isinstance(node.op, ast.UAdd): return +operand
        if isinstance(node.op, ast.USub): return -operand
        if isinstance(node.op, ast.Not): return not operand
        if isinstance(node.op, ast.Invert): return ~operand
        raise NotImplementedError

    def eval_BoolOp(self, node: ast.BoolOp, scope: RuntimeScope) -> Any:
        if isinstance(node.op, ast.And):
            res = True
            for v in node.values:
                res = self.eval_expr(v, scope)
                if not res:
                    return res
            return res
        if isinstance(node.op, ast.Or):
            res = False
            for v in node.values:
                res = self.eval_expr(v, scope)
                if res:
                    return res
            return res
        raise NotImplementedError

    def eval_Compare(self, node: ast.Compare, scope: RuntimeScope) -> bool:
        left = self.eval_expr(node.left, scope)
        for op, comp in zip(node.ops, node.comparators):
            right = self.eval_expr(comp, scope)
            if not self._apply_compare(op, left, right):
                return False
            left = right
        return True

    def eval_IfExp(self, node: ast.IfExp, scope: RuntimeScope) -> Any:
        return self.eval_expr(node.body if self.eval_expr(node.test, scope) else node.orelse, scope)

    def eval_Call(self, node: ast.Call, scope: RuntimeScope) -> Any:
        func = self.eval_expr(node.func, scope)
        args = [self.eval_expr(a, scope) for a in node.args]
        kwargs: Dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None:
                kwargs.update(self.eval_expr(kw.value, scope))
            else:
                kwargs[kw.arg] = self.eval_expr(kw.value, scope)
        return func(*args, **kwargs)

    def eval_List(self, node: ast.List, scope: RuntimeScope) -> list:
        return [self.eval_expr(e, scope) for e in node.elts]

    def eval_Tuple(self, node: ast.Tuple, scope: RuntimeScope) -> tuple:
        return tuple(self.eval_expr(e, scope) for e in node.elts)

    def eval_Set(self, node: ast.Set, scope: RuntimeScope) -> set:
        return {self.eval_expr(e, scope) for e in node.elts}

    def eval_Dict(self, node: ast.Dict, scope: RuntimeScope) -> dict:
        d: Dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                d.update(self.eval_expr(v, scope))
            else:
                d[self.eval_expr(k, scope)] = self.eval_expr(v, scope)
        return d

    def eval_Attribute(self, node: ast.Attribute, scope: RuntimeScope) -> Any:
        obj = self.eval_expr(node.value, scope)
        if isinstance(node.ctx, ast.Load):
            return getattr(obj, node.attr)
        raise NotImplementedError("Attribute ctx other than Load not supported here")

    def eval_Subscript(self, node: ast.Subscript, scope: RuntimeScope) -> Any:
        obj = self.eval_expr(node.value, scope)
        idx = self.eval_expr(node.slice, scope) if not isinstance(node.slice, ast.Slice) else self._eval_slice(node.slice, scope)
        if isinstance(node.ctx, ast.Load):
            return obj[idx]
        raise NotImplementedError("Subscript ctx other than Load not supported here")

    def eval_Slice(self, node: ast.Slice, scope: RuntimeScope) -> slice:
        return self._eval_slice(node, scope)

    # ---- comprehensions (normal) ----

    def eval_ListComp(self, node: ast.ListComp, scope: RuntimeScope) -> list:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: list = []
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        # Outer iterable evaluated in OUTER scope (matches CPython)
        outer_iter = self.eval_expr(gens[0].iter, scope)

        def rec(i: int) -> None:
            if i == len(gens):
                out.append(self.eval_expr(node.elt, comp_scope))
                return
            g = gens[i]
            it = outer_iter if i == 0 else self.eval_expr(g.iter, comp_scope)
            for item in it:
                self._assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    if not self.eval_expr(if_, comp_scope):
                        ok = False
                        break
                if ok:
                    rec(i + 1)

        rec(0)
        return out

    def eval_SetComp(self, node: ast.SetComp, scope: RuntimeScope) -> set:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: set = set()
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")
        outer_iter = self.eval_expr(gens[0].iter, scope)

        def rec(i: int) -> None:
            if i == len(gens):
                out.add(self.eval_expr(node.elt, comp_scope))
                return
            g = gens[i]
            it = outer_iter if i == 0 else self.eval_expr(g.iter, comp_scope)
            for item in it:
                self._assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    if not self.eval_expr(if_, comp_scope):
                        ok = False
                        break
                if ok:
                    rec(i + 1)

        rec(0)
        return out

    def eval_DictComp(self, node: ast.DictComp, scope: RuntimeScope) -> dict:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: dict = {}
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")
        outer_iter = self.eval_expr(gens[0].iter, scope)

        def rec(i: int) -> None:
            if i == len(gens):
                k = self.eval_expr(node.key, comp_scope)
                v = self.eval_expr(node.value, comp_scope)
                out[k] = v
                return
            g = gens[i]
            it = outer_iter if i == 0 else self.eval_expr(g.iter, comp_scope)
            for item in it:
                self._assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    if not self.eval_expr(if_, comp_scope):
                        ok = False
                        break
                if ok:
                    rec(i + 1)

        rec(0)
        return out

    def eval_GeneratorExp(self, node: ast.GeneratorExp, scope: RuntimeScope) -> Iterator[Any]:
        locals_set = _collect_comprehension_locals(node.generators)
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        # Outer iterable evaluated immediately in outer scope (matches Python behavior)
        outer_iter = self.eval_expr(gens[0].iter, scope)

        def gen() -> Iterator[Any]:
            comp_scope = ComprehensionScope(
                scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
            )

            def rec(i: int) -> Iterator[Any]:
                if i == len(gens):
                    yield self.eval_expr(node.elt, comp_scope)
                    return
                g = gens[i]
                it = outer_iter if i == 0 else self.eval_expr(g.iter, comp_scope)
                for item in it:
                    self._assign_target(g.target, item, comp_scope)
                    ok = True
                    for if_ in g.ifs:
                        if not self.eval_expr(if_, comp_scope):
                            ok = False
                            break
                    if ok:
                        yield from rec(i + 1)

            yield from rec(0)

        return gen()

    def eval_Yield(self, node: ast.Yield, scope: RuntimeScope) -> Any:
        raise SyntaxError("yield outside generator execution path (internal error)")

    def eval_YieldFrom(self, node: ast.YieldFrom, scope: RuntimeScope) -> Any:
        raise SyntaxError("yield from outside generator execution path (internal error)")

    # ----------------------------
    # Generator-mode implementations
    # ----------------------------

    # Statements
    def g_exec_Expr(self, node: ast.Expr, scope: RuntimeScope) -> Iterator[Any]:
        yield from self.g_eval_expr(node.value, scope)
        return

    def g_exec_Assign(self, node: ast.Assign, scope: RuntimeScope) -> Iterator[Any]:
        val = yield from self.g_eval_expr(node.value, scope)
        for tgt in node.targets:
            yield from self.g_assign_target(tgt, val, scope)
        return

    def g_exec_AnnAssign(self, node: ast.AnnAssign, scope: RuntimeScope) -> Iterator[Any]:
        if node.value is not None:
            val = yield from self.g_eval_expr(node.value, scope)
            yield from self.g_assign_target(node.target, val, scope)
        if isinstance(node.target, ast.Name):
            ann = yield from self.g_eval_expr(node.annotation, scope)
            ns = scope.class_ns if isinstance(scope, ClassBodyScope) else scope.globals
            anns = ns.get("__annotations__")
            if anns is None:
                anns = {}
                ns["__annotations__"] = anns
            anns[node.target.id] = ann
        return

    def g_exec_AugAssign(self, node: ast.AugAssign, scope: RuntimeScope) -> Iterator[Any]:
        if not isinstance(node.target, ast.Name):
            raise NotImplementedError("AugAssign only supports Name targets here")
        name = node.target.id
        old = scope.load(name)
        rhs = yield from self.g_eval_expr(node.value, scope)
        scope.store(name, self._apply_binop(node.op, old, rhs))
        return

    def g_exec_If(self, node: ast.If, scope: RuntimeScope) -> Iterator[Any]:
        test = yield from self.g_eval_expr(node.test, scope)
        if test:
            yield from self.g_exec_block(node.body, scope)
        else:
            yield from self.g_exec_block(node.orelse, scope)
        return

    def g_exec_While(self, node: ast.While, scope: RuntimeScope) -> Iterator[Any]:
        broke = False
        while True:
            test = yield from self.g_eval_expr(node.test, scope)
            if not test:
                break
            try:
                yield from self.g_exec_block(node.body, scope)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if (not broke) and node.orelse:
            yield from self.g_exec_block(node.orelse, scope)
        return

    def g_exec_For(self, node: ast.For, scope: RuntimeScope) -> Iterator[Any]:
        it = yield from self.g_eval_expr(node.iter, scope)
        broke = False
        for item in it:
            yield from self.g_assign_target(node.target, item, scope)
            try:
                yield from self.g_exec_block(node.body, scope)
            except ContinueSignal:
                continue
            except BreakSignal:
                broke = True
                break
        if (not broke) and node.orelse:
            yield from self.g_exec_block(node.orelse, scope)
        return

    def g_exec_Break(self, node: ast.Break, scope: RuntimeScope) -> Iterator[Any]:
        raise BreakSignal()

    def g_exec_Continue(self, node: ast.Continue, scope: RuntimeScope) -> Iterator[Any]:
        raise ContinueSignal()

    def g_exec_Return(self, node: ast.Return, scope: RuntimeScope) -> Iterator[Any]:
        val = (yield from self.g_eval_expr(node.value, scope)) if node.value is not None else None
        raise ReturnSignal(val)

    def g_exec_Delete(self, node: ast.Delete, scope: RuntimeScope) -> Iterator[Any]:
        for tgt in node.targets:
            yield from self.g_delete_target(tgt, scope)
        return

    def g_exec_FunctionDef(self, node: ast.FunctionDef, scope: RuntimeScope) -> Iterator[Any]:
        defaults = []
        for d in (node.args.defaults or []):
            defaults.append((yield from self.g_eval_expr(d, scope)))
        kw_defaults = []
        for d in (getattr(node.args, "kw_defaults", []) or []):
            kw_defaults.append((yield from self.g_eval_expr(d, scope)) if d is not None else None)

        fn_table = scope.code.lookup_function_table(node)
        fn_scope_info = scope.code.scope_info_for(fn_table)
        closure = {name: scope.capture_cell(name) for name in fn_scope_info.frees}
        is_gen = _contains_yield(node)

        func = UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            scope_info=fn_scope_info,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=is_gen,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = yield from self.g_eval_expr(dec_node, scope)
            decorated = dec(decorated)

        scope.store(node.name, decorated)
        return

    def g_exec_ClassDef(self, node: ast.ClassDef, scope: RuntimeScope) -> Iterator[Any]:
        bases = []
        for b in node.bases:
            bases.append((yield from self.g_eval_expr(b, scope)))
        kw: Dict[str, Any] = {}
        for k in node.keywords:
            if k.arg is None:
                kw.update((yield from self.g_eval_expr(k.value, scope)))
            else:
                kw[k.arg] = (yield from self.g_eval_expr(k.value, scope))

        meta = kw.pop("metaclass", None)
        if meta is None:
            meta = type(bases[0]) if bases else type

        class_ns: Dict[str, Any] = {}
        class_ns.setdefault("__module__", scope.globals.get("__name__", "__main__"))
        class_ns.setdefault("__qualname__", node.name)

        body_scope = ClassBodyScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, class_ns=class_ns)
        # class body itself cannot yield (syntax), so normal exec is OK:
        self.exec_block(node.body, body_scope)

        cls = meta(node.name, tuple(bases), class_ns, **kw)

        decorated: Any = cls
        for dec_node in reversed(node.decorator_list or []):
            dec = yield from self.g_eval_expr(dec_node, scope)
            decorated = dec(decorated)

        scope.store(node.name, decorated)
        return

    def g_exec_Try(self, node: ast.Try, scope: RuntimeScope) -> Iterator[Any]:
        try:
            yield from self.g_exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise
            handled = False
            for handler in node.handlers:
                if handler.type is None:
                    match = True
                else:
                    exc_type = yield from self.g_eval_expr(handler.type, scope)
                    match = isinstance(e, exc_type)
                if match:
                    handled = True
                    if handler.name:
                        scope.store(handler.name, e)
                    try:
                        yield from self.g_exec_block(handler.body, scope)
                    finally:
                        if handler.name:
                            scope.unbind(handler.name)
                    break
            if not handled:
                raise
        else:
            if node.orelse:
                yield from self.g_exec_block(node.orelse, scope)
        finally:
            if node.finalbody:
                yield from self.g_exec_block(node.finalbody, scope)
        return

    def g_exec_Raise(self, node: ast.Raise, scope: RuntimeScope) -> Iterator[Any]:
        if node.exc is None:
            raise RuntimeError("re-raise not supported in this interpreter")
        exc = yield from self.g_eval_expr(node.exc, scope)
        if isinstance(exc, BaseException):
            raise exc
        if isinstance(exc, type) and issubclass(exc, BaseException):
            raise exc()
        raise TypeError("Can only raise exception instances or exception classes")

    def g_exec_With(self, node: ast.With, scope: RuntimeScope) -> Iterator[Any]:
        exits = []
        try:
            for item in node.items:
                mgr = yield from self.g_eval_expr(item.context_expr, scope)
                enter = getattr(mgr, "__enter__")
                exit_ = getattr(mgr, "__exit__")
                val = enter()
                exits.append(exit_)
                if item.optional_vars is not None:
                    yield from self.g_assign_target(item.optional_vars, val, scope)

            yield from self.g_exec_block(node.body, scope)

        except ControlFlowSignal:
            for exit_ in reversed(exits):
                exit_(None, None, None)
            raise

        except BaseException as e:
            exc_type = type(e)
            exc = e
            tb = e.__traceback__

            for exit_ in reversed(exits):
                try:
                    suppress = exit_(exc_type, exc, tb)
                except BaseException as new_e:
                    exc_type = type(new_e)
                    exc = new_e
                    tb = new_e.__traceback__
                    continue
                if suppress:
                    exc_type = exc = tb = None

            if exc_type is None:
                return
            raise exc

        else:
            for exit_ in reversed(exits):
                exit_(None, None, None)

        return

    def g_exec_Import(self, node: ast.Import, scope: RuntimeScope) -> Iterator[Any]:
        self.exec_Import(node, scope)
        return
        yield  # unreachable

    def g_exec_ImportFrom(self, node: ast.ImportFrom, scope: RuntimeScope) -> Iterator[Any]:
        self.exec_ImportFrom(node, scope)
        return
        yield

    def g_exec_Global(self, node: ast.Global, scope: RuntimeScope) -> Iterator[Any]:
        return
        yield

    def g_exec_Nonlocal(self, node: ast.Nonlocal, scope: RuntimeScope) -> Iterator[Any]:
        return
        yield

    # Expressions (generator mode)
    def g_eval_Constant(self, node: ast.Constant, scope: RuntimeScope) -> Iterator[Any]:
        return node.value
        yield

    def g_eval_Name(self, node: ast.Name, scope: RuntimeScope) -> Iterator[Any]:
        return scope.load(node.id)
        yield

    def g_eval_BinOp(self, node: ast.BinOp, scope: RuntimeScope) -> Iterator[Any]:
        left = yield from self.g_eval_expr(node.left, scope)
        right = yield from self.g_eval_expr(node.right, scope)
        return self._apply_binop(node.op, left, right)

    def g_eval_UnaryOp(self, node: ast.UnaryOp, scope: RuntimeScope) -> Iterator[Any]:
        operand = yield from self.g_eval_expr(node.operand, scope)
        if isinstance(node.op, ast.UAdd): return +operand
        if isinstance(node.op, ast.USub): return -operand
        if isinstance(node.op, ast.Not): return not operand
        if isinstance(node.op, ast.Invert): return ~operand
        raise NotImplementedError

    def g_eval_BoolOp(self, node: ast.BoolOp, scope: RuntimeScope) -> Iterator[Any]:
        if isinstance(node.op, ast.And):
            res = True
            for v in node.values:
                res = yield from self.g_eval_expr(v, scope)
                if not res:
                    return res
            return res
        if isinstance(node.op, ast.Or):
            res = False
            for v in node.values:
                res = yield from self.g_eval_expr(v, scope)
                if res:
                    return res
            return res
        raise NotImplementedError

    def g_eval_Compare(self, node: ast.Compare, scope: RuntimeScope) -> Iterator[bool]:
        left = yield from self.g_eval_expr(node.left, scope)
        for op, comp in zip(node.ops, node.comparators):
            right = yield from self.g_eval_expr(comp, scope)
            if not self._apply_compare(op, left, right):
                return False
            left = right
        return True

    def g_eval_IfExp(self, node: ast.IfExp, scope: RuntimeScope) -> Iterator[Any]:
        test = yield from self.g_eval_expr(node.test, scope)
        if test:
            return (yield from self.g_eval_expr(node.body, scope))
        return (yield from self.g_eval_expr(node.orelse, scope))

    def g_eval_Call(self, node: ast.Call, scope: RuntimeScope) -> Iterator[Any]:
        func = yield from self.g_eval_expr(node.func, scope)
        args = []
        for a in node.args:
            args.append((yield from self.g_eval_expr(a, scope)))
        kwargs: Dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None:
                kwargs.update((yield from self.g_eval_expr(kw.value, scope)))
            else:
                kwargs[kw.arg] = (yield from self.g_eval_expr(kw.value, scope))
        return func(*args, **kwargs)

    def g_eval_List(self, node: ast.List, scope: RuntimeScope) -> Iterator[list]:
        out = []
        for e in node.elts:
            out.append((yield from self.g_eval_expr(e, scope)))
        return out

    def g_eval_Tuple(self, node: ast.Tuple, scope: RuntimeScope) -> Iterator[tuple]:
        out = []
        for e in node.elts:
            out.append((yield from self.g_eval_expr(e, scope)))
        return tuple(out)

    def g_eval_Set(self, node: ast.Set, scope: RuntimeScope) -> Iterator[set]:
        out = set()
        for e in node.elts:
            out.add((yield from self.g_eval_expr(e, scope)))
        return out

    def g_eval_Dict(self, node: ast.Dict, scope: RuntimeScope) -> Iterator[dict]:
        d: Dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                d.update((yield from self.g_eval_expr(v, scope)))
            else:
                kk = (yield from self.g_eval_expr(k, scope))
                vv = (yield from self.g_eval_expr(v, scope))
                d[kk] = vv
        return d

    def g_eval_Attribute(self, node: ast.Attribute, scope: RuntimeScope) -> Iterator[Any]:
        obj = yield from self.g_eval_expr(node.value, scope)
        return getattr(obj, node.attr)

    def g_eval_Subscript(self, node: ast.Subscript, scope: RuntimeScope) -> Iterator[Any]:
        obj = yield from self.g_eval_expr(node.value, scope)
        idx = yield from self.g_eval_expr(node.slice, scope)
        return obj[idx]

    def g_eval_Slice(self, node: ast.Slice, scope: RuntimeScope) -> Iterator[slice]:
        lo = (yield from self.g_eval_expr(node.lower, scope)) if node.lower else None
        hi = (yield from self.g_eval_expr(node.upper, scope)) if node.upper else None
        st = (yield from self.g_eval_expr(node.step, scope)) if node.step else None
        return slice(lo, hi, st)

    # comprehensions (generator-mode)
    def g_eval_ListComp(self, node: ast.ListComp, scope: RuntimeScope) -> Iterator[list]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: list = []
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                val = yield from self.g_eval_expr(node.elt, comp_scope)
                out.append(val)
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))
            for item in it:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

        yield from rec(0)
        return out

    def g_eval_SetComp(self, node: ast.SetComp, scope: RuntimeScope) -> Iterator[set]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: set = set()
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                val = yield from self.g_eval_expr(node.elt, comp_scope)
                out.add(val)
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))
            for item in it:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

        yield from rec(0)
        return out

    def g_eval_DictComp(self, node: ast.DictComp, scope: RuntimeScope) -> Iterator[dict]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

        out: dict = {}
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                k = yield from self.g_eval_expr(node.key, comp_scope)
                v = yield from self.g_eval_expr(node.value, comp_scope)
                out[k] = v
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))
            for item in it:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

        yield from rec(0)
        return out

    def g_eval_GeneratorExp(self, node: ast.GeneratorExp, scope: RuntimeScope) -> Iterator[Iterator[Any]]:
        locals_set = _collect_comprehension_locals(node.generators)
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def make_gen() -> Iterator[Any]:
            comp_scope = ComprehensionScope(scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set)

            def rec(i: int) -> Iterator[Any]:
                if i == len(gens):
                    val = yield from self.g_eval_expr(node.elt, comp_scope)
                    yield val
                    return
                g = gens[i]
                it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))
                for item in it:
                    yield from self.g_assign_target(g.target, item, comp_scope)
                    ok = True
                    for if_ in g.ifs:
                        cond = yield from self.g_eval_expr(if_, comp_scope)
                        if not cond:
                            ok = False
                            break
                    if ok:
                        yield from rec(i + 1)

            yield from rec(0)

        return make_gen()

    # yield / yield from
    def g_eval_Yield(self, node: ast.Yield, scope: RuntimeScope) -> Iterator[Any]:
        if node.value is None:
            sent = (yield None)
            return sent
        val = yield from self.g_eval_expr(node.value, scope)
        sent = (yield val)
        return sent

    def g_eval_YieldFrom(self, node: ast.YieldFrom, scope: RuntimeScope) -> Iterator[Any]:
        it = yield from self.g_eval_expr(node.value, scope)
        # delegate send/throw/close correctly
        result = yield from it
        return result

    # ----------------------------
    # Target helpers (normal + generator)
    # ----------------------------

    def _assign_target(self, target: ast.AST, value: Any, scope: RuntimeScope) -> None:
        if isinstance(target, ast.Name):
            scope.store(target.id, value)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            items = list(value)
            if len(items) != len(target.elts):
                raise ValueError("unpack mismatch")
            for elt, item in zip(target.elts, items):
                self._assign_target(elt, item, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = self.eval_expr(target.value, scope)
            setattr(obj, target.attr, value)
            return
        if isinstance(target, ast.Subscript):
            obj = self.eval_expr(target.value, scope)
            idx = self.eval_expr(target.slice, scope) if not isinstance(target.slice, ast.Slice) else self._eval_slice(target.slice, scope)
            obj[idx] = value
            return
        raise NotImplementedError(f"Assignment target not supported: {target.__class__.__name__}")

    def g_assign_target(self, target: ast.AST, value: Any, scope: RuntimeScope) -> Iterator[Any]:
        if isinstance(target, ast.Name):
            scope.store(target.id, value)
            return
            yield
        if isinstance(target, (ast.Tuple, ast.List)):
            items = list(value)
            if len(items) != len(target.elts):
                raise ValueError("unpack mismatch")
            for elt, item in zip(target.elts, items):
                yield from self.g_assign_target(elt, item, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = yield from self.g_eval_expr(target.value, scope)
            setattr(obj, target.attr, value)
            return
        if isinstance(target, ast.Subscript):
            obj = yield from self.g_eval_expr(target.value, scope)
            idx = yield from self.g_eval_expr(target.slice, scope)
            obj[idx] = value
            return
        raise NotImplementedError(f"Assignment target not supported: {target.__class__.__name__}")

    def _delete_target(self, target: ast.AST, scope: RuntimeScope) -> None:
        if isinstance(target, ast.Name):
            scope.delete(target.id)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._delete_target(elt, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = self.eval_expr(target.value, scope)
            delattr(obj, target.attr)
            return
        if isinstance(target, ast.Subscript):
            obj = self.eval_expr(target.value, scope)
            idx = self.eval_expr(target.slice, scope) if not isinstance(target.slice, ast.Slice) else self._eval_slice(target.slice, scope)
            del obj[idx]
            return
        raise NotImplementedError(f"del target not supported: {target.__class__.__name__}")

    def g_delete_target(self, target: ast.AST, scope: RuntimeScope) -> Iterator[Any]:
        if isinstance(target, ast.Name):
            scope.delete(target.id)
            return
            yield
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                yield from self.g_delete_target(elt, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = yield from self.g_eval_expr(target.value, scope)
            delattr(obj, target.attr)
            return
        if isinstance(target, ast.Subscript):
            obj = yield from self.g_eval_expr(target.value, scope)
            idx = yield from self.g_eval_expr(target.slice, scope)
            del obj[idx]
            return
        raise NotImplementedError(f"del target not supported: {target.__class__.__name__}")

    def _eval_slice(self, node: ast.Slice, scope: RuntimeScope) -> slice:
        lo = self.eval_expr(node.lower, scope) if node.lower else None
        hi = self.eval_expr(node.upper, scope) if node.upper else None
        st = self.eval_expr(node.step, scope) if node.step else None
        return slice(lo, hi, st)

    # ----------------------------
    # operators
    # ----------------------------

    def _apply_binop(self, op: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add): return left + right
        if isinstance(op, ast.Sub): return left - right
        if isinstance(op, ast.Mult): return left * right
        if isinstance(op, ast.Div): return left / right
        if isinstance(op, ast.FloorDiv): return left // right
        if isinstance(op, ast.Mod): return left % right
        if isinstance(op, ast.Pow): return left ** right
        if isinstance(op, ast.BitAnd): return left & right
        if isinstance(op, ast.BitOr): return left | right
        if isinstance(op, ast.BitXor): return left ^ right
        if isinstance(op, ast.LShift): return left << right
        if isinstance(op, ast.RShift): return left >> right
        if isinstance(op, ast.MatMult): return left @ right
        raise NotImplementedError(f"BinOp {op.__class__.__name__} not supported")

    def _apply_compare(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq): return left == right
        if isinstance(op, ast.NotEq): return left != right
        if isinstance(op, ast.Lt): return left < right
        if isinstance(op, ast.LtE): return left <= right
        if isinstance(op, ast.Gt): return left > right
        if isinstance(op, ast.GtE): return left >= right
        if isinstance(op, ast.Is): return left is right
        if isinstance(op, ast.IsNot): return left is not right
        if isinstance(op, ast.In): return left in right
        if isinstance(op, ast.NotIn): return left not in right
        raise NotImplementedError(f"Compare {op.__class__.__name__} not supported")

    # ----------------------------
    # Function call binding + generator support
    # ----------------------------

    def _call_user_function(self, func_obj: UserFunction, args: tuple, kwargs: dict) -> Any:
        node = func_obj.node
        si = func_obj.scope_info
        call_scope = FunctionScope(func_obj.code, func_obj.globals, self.builtins, si, func_obj.closure)

        def is_bound(name: str) -> bool:
            if name in si.cellvars:
                return call_scope.cells[name].value is not UNBOUND
            return name in call_scope.locals

        posonly = getattr(node.args, "posonlyargs", []) or []
        pos_or_kw = getattr(node.args, "args", []) or []
        params_nodes = posonly + pos_or_kw
        params = [a.arg for a in params_nodes]

        default_map: Dict[str, Any] = {}
        if func_obj.defaults:
            for name, val in zip(params[-len(func_obj.defaults):], func_obj.defaults):
                default_map[name] = val

        # positional binding
        if len(args) > len(params) and node.args.vararg is None:
            raise TypeError(f"{node.name}() takes {len(params)} positional args but {len(args)} were given")

        for name, val in zip(params, args):
            call_scope.store(name, val)

        extra_pos = args[len(params):]
        if extra_pos:
            if node.args.vararg is None:
                raise TypeError("varargs not supported")
            call_scope.store(node.args.vararg.arg, tuple(extra_pos))

        # keyword binding
        for k, v in kwargs.items():
            if k in params:
                if any(k == a.arg for a in posonly):
                    raise TypeError(f"{node.name}() got positional-only arg '{k}' passed as keyword")
                if is_bound(k):
                    raise TypeError(f"{node.name}() got multiple values for argument '{k}'")
                call_scope.store(k, v)
            else:
                if node.args.kwarg is None:
                    raise TypeError(f"{node.name}() got unexpected keyword argument '{k}'")
                kwarg_name = node.args.kwarg.arg
                if not is_bound(kwarg_name):
                    call_scope.store(kwarg_name, {})
                d = call_scope.load(kwarg_name)
                d[k] = v

        # fill required + defaults
        for name in params:
            if not is_bound(name):
                if name in default_map:
                    call_scope.store(name, default_map[name])
                else:
                    raise TypeError(f"{node.name}() missing required argument '{name}'")

        # kw-only
        kwonlyargs = getattr(node.args, "kwonlyargs", []) or []
        if kwonlyargs:
            for arg_node, default_val in zip(kwonlyargs, func_obj.kw_defaults):
                name = arg_node.arg
                if not is_bound(name):
                    if default_val is not None:
                        call_scope.store(name, default_val)
                    else:
                        raise TypeError(f"{node.name}() missing required keyword-only argument '{name}'")

        # ensure vararg/kwarg exist
        if node.args.vararg is not None and not is_bound(node.args.vararg.arg):
            call_scope.store(node.args.vararg.arg, ())
        if node.args.kwarg is not None and not is_bound(node.args.kwarg.arg):
            call_scope.store(node.args.kwarg.arg, {})

        # normal function executes immediately
        if not func_obj.is_generator:
            try:
                self.exec_block(node.body, call_scope)
            except ReturnSignal as r:
                return r.value
            return None

        # generator function returns a real Python generator to allow pausing/resuming
        def runner():
            try:
                yield from self.g_exec_block(node.body, call_scope)
            except ReturnSignal as r:
                return r.value

        return runner()


# ----------------------------
# Demo: interpreter interpreting itself interpreting itself
# ----------------------------

if __name__ == "__main__":
    interp1 = Interpreter(allowed_imports={"math"})

    code3 = """
print("=== level 3 ===")
try:
    import os
except Exception as e:
    print("import blocked:", type(e).__name__)

def f():
    return [x for x in range(3)]
print("f() =", f())
"""

    code2 = """
import math
print("=== level 2 ===")

class Counter:
    def __init__(self, start):
        self.x = start
    def inc(self):
        self.x = self.x + 1
        return self.x

def gen(n):
    i = 0
    while i < n:
        yield i
        i = i + 1
    return "done"

def run():
    c = Counter(10)
    print("c.inc()", c.inc())

    squares = [i*i for i in range(5)]
    d = {i: i+1 for i in range(3) if i != 1}
    g = (i+100 for i in range(3))
    print("squares", squares)
    print("dict", d)
    print("genexp", list(g))

    tmp = 5
    del tmp
    try:
        print(tmp)
    except Exception as e:
        print("del ->", type(e).__name__)

    gg = gen(3)
    for v in gg:
        print("yielded", v)

    inner2 = Interpreter(allowed_imports=set())
    inner2.run(CODE3, env={})

run()
"""

    code1 = """
print("=== level 1 ===")

def fib(n):
    a = 0
    b = 1
    out = []
    i = 0
    while i < n:
        out.append(a)
        a, b = b, a + b
        i = i + 1
    return out

print("fib(7) =", fib(7))

inner = Interpreter(allowed_imports={"math"})
inner.run(CODE2, env={"Interpreter": Interpreter, "CODE3": CODE3})
"""

    interp1.run(code1, env={"Interpreter": Interpreter, "CODE2": code2, "CODE3": code3})
