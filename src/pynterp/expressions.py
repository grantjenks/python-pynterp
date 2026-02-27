from __future__ import annotations

import ast
from typing import Any, Dict, Iterator

from .scopes import ComprehensionScope, RuntimeScope
from .symtable_utils import _collect_comprehension_locals


class ExpressionMixin:
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
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.Invert):
            return ~operand
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
        idx = (
            self.eval_expr(node.slice, scope)
            if not isinstance(node.slice, ast.Slice)
            else self._eval_slice(node.slice, scope)
        )
        if isinstance(node.ctx, ast.Load):
            return obj[idx]
        raise NotImplementedError("Subscript ctx other than Load not supported here")

    def eval_Slice(self, node: ast.Slice, scope: RuntimeScope) -> slice:
        return self._eval_slice(node, scope)

    # ---- comprehensions (normal) ----

    def eval_ListComp(self, node: ast.ListComp, scope: RuntimeScope) -> list:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.Invert):
            return ~operand
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
                kwargs[kw.arg] = yield from self.g_eval_expr(kw.value, scope)
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
                kk = yield from self.g_eval_expr(k, scope)
                vv = yield from self.g_eval_expr(v, scope)
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
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

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

    def g_eval_GeneratorExp(
        self, node: ast.GeneratorExp, scope: RuntimeScope
    ) -> Iterator[Iterator[Any]]:
        locals_set = _collect_comprehension_locals(node.generators)
        gens = node.generators
        if any(getattr(g, "is_async", False) for g in gens):
            raise NotImplementedError("async comprehensions not supported")

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def make_gen() -> Iterator[Any]:
            comp_scope = ComprehensionScope(
                scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
            )

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
            sent = yield None
            return sent
        val = yield from self.g_eval_expr(node.value, scope)
        sent = yield val
        return sent

    def g_eval_YieldFrom(self, node: ast.YieldFrom, scope: RuntimeScope) -> Iterator[Any]:
        it = yield from self.g_eval_expr(node.value, scope)
        # delegate send/throw/close correctly
        result = yield from it
        return result

    # ----------------------------
    # Target helpers (normal + generator)
    # ----------------------------
