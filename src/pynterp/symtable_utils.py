from __future__ import annotations

import ast
import symtable
from typing import Set


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
