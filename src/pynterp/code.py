from __future__ import annotations

import ast
import symtable
from typing import Dict, Set

from .symtable_utils import _table_frees


def _build_symtable(source: str, filename: str) -> symtable.SymbolTable:
    try:
        return symtable.symtable(source, filename, "exec")
    except TypeError as exc:
        # CPython 3.14's Lib/symtable.py passes module=<...> as a keyword-only
        # argument to _symtable.symtable(). Older host runtimes reject that call.
        if "_symtable.symtable() takes no keyword arguments" not in str(exc):
            raise
        import _symtable

        raw_table = _symtable.symtable(source, filename, "exec")
        new_symbol_table = getattr(symtable, "_newSymbolTable", None)
        if callable(new_symbol_table):
            return new_symbol_table(raw_table, filename)
        raise


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
        self.sym_root = _build_symtable(source, filename)

        self._tables_by_key: Dict[tuple[str, str, int], list[symtable.SymbolTable]] = {}
        self._cellvars_by_id: Dict[int, Set[str]] = {}
        self._lambda_occurrence_by_location: Dict[tuple[int, int], int] = {}

        self._index_tables(self.sym_root)
        self._index_lambda_occurrences()
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

    def _index_lambda_occurrences(self) -> None:
        lambda_counts_by_line: Dict[int, int] = {}

        class Visitor(ast.NodeVisitor):
            def _visit_lambda_default_exprs(self, node: ast.Lambda) -> None:
                for default in node.args.defaults or []:
                    self.visit(default)
                for kw_default in getattr(node.args, "kw_defaults", []) or []:
                    if kw_default is not None:
                        self.visit(kw_default)

            def visit_Lambda(self, node: ast.Lambda) -> None:
                # Match symtable ordering: lambda defaults are analyzed in the
                # enclosing scope before the lambda scope itself is registered.
                self._visit_lambda_default_exprs(node)
                index = lambda_counts_by_line.get(node.lineno, 0)
                lambda_counts_by_line[node.lineno] = index + 1
                self_outer._lambda_occurrence_by_location[(node.lineno, node.col_offset)] = index
                self.visit(node.body)

        self_outer = self
        Visitor().visit(self.tree)

    def lookup_function_table(
        self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> symtable.Function:
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

    def lookup_lambda_table(self, lambda_node: ast.Lambda) -> symtable.Function:
        key = ("function", "lambda", lambda_node.lineno)
        tables = self._tables_by_key.get(key, [])
        if not tables:
            raise RuntimeError(
                "Could not find symtable for lambda at "
                f"line {lambda_node.lineno}:{lambda_node.col_offset}"
            )
        if len(tables) == 1:
            tbl = tables[0]
        else:
            location = (lambda_node.lineno, lambda_node.col_offset)
            index = self._lambda_occurrence_by_location.get(location)
            if index is None or index >= len(tables):
                raise RuntimeError(
                    "Ambiguous symtable match for lambda at "
                    f"line {lambda_node.lineno}:{lambda_node.col_offset}"
                )
            tbl = tables[index]
        if not isinstance(tbl, symtable.Function):
            raise RuntimeError("lookup_lambda_table returned non-function table")
        return tbl

    def scope_info_for(self, fn_table: symtable.Function) -> ScopeInfo:
        return ScopeInfo(fn_table, self._cellvars_by_id.get(fn_table.get_id(), set()))
