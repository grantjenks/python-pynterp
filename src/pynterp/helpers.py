from __future__ import annotations

import ast
from typing import Any, Dict, Iterator

from .common import UNBOUND, ReturnSignal
from .functions import UserFunction
from .scopes import FunctionScope, RuntimeScope


class HelperMixin:
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
            idx = (
                self.eval_expr(target.slice, scope)
                if not isinstance(target.slice, ast.Slice)
                else self._eval_slice(target.slice, scope)
            )
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
            idx = (
                self.eval_expr(target.slice, scope)
                if not isinstance(target.slice, ast.Slice)
                else self._eval_slice(target.slice, scope)
            )
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
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left**right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right
        if isinstance(op, ast.BitXor):
            return left ^ right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        if isinstance(op, ast.MatMult):
            return left @ right
        raise NotImplementedError(f"BinOp {op.__class__.__name__} not supported")

    def _apply_compare(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        raise NotImplementedError(f"Compare {op.__class__.__name__} not supported")

    # ----------------------------
    # Function call binding + generator support
    # ----------------------------

    def _call_user_function(self, func_obj: UserFunction, args: tuple, kwargs: dict) -> Any:
        node = func_obj.node
        si = func_obj.scope_info
        call_scope = FunctionScope(
            func_obj.code, func_obj.globals, func_obj.builtins, si, func_obj.closure
        )

        def is_bound(name: str) -> bool:
            if name in si.cellvars:
                return call_scope.cells[name].value is not UNBOUND
            return name in call_scope.locals

        posonly = getattr(node.args, "posonlyargs", []) or []
        pos_or_kw = getattr(node.args, "args", []) or []
        kwonlyargs = getattr(node.args, "kwonlyargs", []) or []
        params_nodes = posonly + pos_or_kw
        params = [a.arg for a in params_nodes]
        kwonly_names = {a.arg for a in kwonlyargs}

        default_map: Dict[str, Any] = {}
        if func_obj.defaults:
            for name, val in zip(params[-len(func_obj.defaults) :], func_obj.defaults):
                default_map[name] = val

        # positional binding
        if len(args) > len(params) and node.args.vararg is None:
            raise TypeError(
                f"{node.name}() takes {len(params)} positional args but {len(args)} were given"
            )

        for name, val in zip(params, args):
            call_scope.store(name, val)

        extra_pos = args[len(params) :]
        if extra_pos:
            if node.args.vararg is None:
                raise TypeError("varargs not supported")
            call_scope.store(node.args.vararg.arg, tuple(extra_pos))

        # keyword binding
        for k, v in kwargs.items():
            if k in params or k in kwonly_names:
                if any(k == a.arg for a in posonly):
                    raise TypeError(
                        f"{node.name}() got positional-only arg '{k}' passed as keyword"
                    )
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
        if kwonlyargs:
            for arg_node, default_val in zip(kwonlyargs, func_obj.kw_defaults):
                name = arg_node.arg
                if not is_bound(name):
                    if default_val is not None:
                        call_scope.store(name, default_val)
                    else:
                        raise TypeError(
                            f"{node.name}() missing required keyword-only argument '{name}'"
                        )

        # ensure vararg/kwarg exist
        if node.args.vararg is not None and not is_bound(node.args.vararg.arg):
            call_scope.store(node.args.vararg.arg, ())
        if node.args.kwarg is not None and not is_bound(node.args.kwarg.arg):
            call_scope.store(node.args.kwarg.arg, {})

        if not hasattr(self, "_call_stack"):
            self._call_stack = []
        frame = (func_obj, call_scope)

        # normal function executes immediately
        if not func_obj.is_generator:
            self._call_stack.append(frame)
            try:
                try:
                    self.exec_block(node.body, call_scope)
                except ReturnSignal as r:
                    return r.value
                return None
            finally:
                self._call_stack.pop()

        # generator function returns a real Python generator to allow pausing/resuming
        def runner():
            self._call_stack.append(frame)
            try:
                try:
                    yield from self.g_exec_block(node.body, call_scope)
                except ReturnSignal as r:
                    return r.value
            finally:
                self._call_stack.pop()

        return runner()
