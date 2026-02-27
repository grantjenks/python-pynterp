from __future__ import annotations

import ast
import symtable
from typing import Dict, Set

from .symtable_utils import _table_frees


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
