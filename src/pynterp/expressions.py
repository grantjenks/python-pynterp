from __future__ import annotations

import ast
import builtins
from typing import Any, Callable, Dict, Iterator

from .common import NO_DEFAULT, UNBOUND, AwaitRequest
from .functions import UserFunction
from .helpers import InterpretedAsyncGenerator
from .lib.guards import guard_attr_name
from .scopes import ComprehensionScope, RuntimeScope
from .symtable_utils import _collect_comprehension_locals

_NO_SUPER = object()
_TYPING_RUNTIME_FACTORIES = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple", "NewType"})

try:  # Python < 3.14 has no t-string runtime objects.
    from string.templatelib import Interpolation as TemplateInterpolation
    from string.templatelib import Template as TemplateString
except ImportError:  # pragma: no cover - exercised only on older runtimes.
    TemplateInterpolation = None
    TemplateString = None


class ExpressionMixin:
    def _maybe_fix_typing_runtime_module(self, func: Any, result: Any, scope: RuntimeScope) -> Any:
        if getattr(func, "__module__", None) != "typing":
            return result
        if getattr(func, "__name__", None) not in _TYPING_RUNTIME_FACTORIES:
            return result
        module_name = scope.globals.get("__name__")
        if not isinstance(module_name, str) or not module_name:
            return result
        if getattr(result, "__module__", None) != __name__:
            return result
        try:
            setattr(result, "__module__", module_name)
        except Exception:
            pass
        return result

    def _template_conversion(self, conversion: int) -> str | None:
        if conversion == -1:
            return None
        if conversion == 115:  # !s
            return "s"
        if conversion == 114:  # !r
            return "r"
        if conversion == 97:  # !a
            return "a"
        raise NotImplementedError(f"Unsupported template conversion {conversion!r}")

    def _build_template_interpolation(
        self, value: Any, expression: str | None, conversion: int, format_spec: str
    ) -> Any:
        if TemplateInterpolation is None:
            raise NotImplementedError("TemplateStr is not supported on this Python runtime")
        return TemplateInterpolation(
            value, expression if expression is not None else "", self._template_conversion(conversion), format_spec
        )

    def _callable_name(self, func: Any) -> str:
        return getattr(func, "__name__", type(func).__name__)

    def _store_keyword(self, func: Any, kwargs: Dict[str, Any], key: str, value: Any) -> None:
        if key in kwargs:
            name = self._callable_name(func)
            raise TypeError(f"{name}() got multiple values for keyword argument '{key}'")
        kwargs[key] = value

    def _merge_keyword_mapping(self, func: Any, kwargs: Dict[str, Any], mapping: Any) -> None:
        if not hasattr(mapping, "keys"):
            name = self._callable_name(func)
            raise TypeError(
                f"{name}() argument after ** must be a mapping, not {type(mapping).__name__}"
            )
        for key in mapping.keys():
            if not isinstance(key, str):
                raise TypeError("keywords must be strings")
            self._store_keyword(func, kwargs, key, mapping[key])

    def _maybe_zero_arg_super(self, func: Any, args: list[Any], kwargs: Dict[str, Any]) -> Any:
        if func is not builtins.super or args or kwargs:
            return _NO_SUPER

        call_stack = getattr(self, "_call_stack", [])
        if not call_stack:
            return _NO_SUPER

        func_obj, call_scope = call_stack[-1]
        class_cell = func_obj.closure.get("__class__")
        if class_cell is None or class_cell.value is UNBOUND:
            raise RuntimeError("super(): __class__ cell not found")

        params = (getattr(func_obj.node.args, "posonlyargs", []) or []) + (
            getattr(func_obj.node.args, "args", []) or []
        )
        if not params:
            raise RuntimeError("super(): no arguments")

        first_arg_name = params[0].arg
        try:
            first_arg_value = call_scope.load(first_arg_name)
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError("super(): no arguments") from exc

        return builtins.super(class_cell.value, first_arg_value)

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

    def _namedexpr_store_scope(self, scope: RuntimeScope) -> RuntimeScope:
        target_scope = scope
        while isinstance(target_scope, ComprehensionScope):
            target_scope = target_scope.outer_scope
        return target_scope

    def _store_namedexpr_target(self, target: ast.expr, value: Any, scope: RuntimeScope) -> None:
        if not isinstance(target, ast.Name):
            raise NotImplementedError(
                f"NamedExpr target not supported: {target.__class__.__name__}"
            )
        self._namedexpr_store_scope(scope).store(target.id, value)

    def eval_NamedExpr(self, node: ast.NamedExpr, scope: RuntimeScope) -> Any:
        value = self.eval_expr(node.value, scope)
        self._store_namedexpr_target(node.target, value, scope)
        return value

    def eval_Lambda(self, node: ast.Lambda, scope: RuntimeScope) -> UserFunction:
        defaults = [self.eval_expr(d, scope) for d in (node.args.defaults or [])]
        kw_defaults = [
            (self.eval_expr(d, scope) if d is not None else NO_DEFAULT)
            for d in (getattr(node.args, "kw_defaults", []) or [])
        ]
        lambda_table = scope.code.lookup_lambda_table(node)
        lambda_scope_info = scope.code.scope_info_for(lambda_table)
        closure = {name: scope.capture_cell(name) for name in lambda_scope_info.frees}
        return UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            builtins_dict=scope.builtins,
            scope_info=lambda_scope_info,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=False,
            qualname=self._qualname_for_definition("<lambda>", scope),
            private_owner=getattr(scope, "private_owner", None),
        )

    def eval_Call(self, node: ast.Call, scope: RuntimeScope) -> Any:
        func = self.eval_expr(node.func, scope)
        args: list[Any] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                args.extend(self.eval_expr(arg.value, scope))
            else:
                args.append(self.eval_expr(arg, scope))
        kwargs: Dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None:
                mapping = self.eval_expr(kw.value, scope)
                self._merge_keyword_mapping(func, kwargs, mapping)
            else:
                value = self.eval_expr(kw.value, scope)
                self._store_keyword(func, kwargs, kw.arg, value)
        super_value = self._maybe_zero_arg_super(func, args, kwargs)
        if super_value is not _NO_SUPER:
            return super_value
        if kwargs:
            result = func(*args, **kwargs)
        else:
            result = func(*args)
        result = self._adapt_runtime_value(result)
        return self._maybe_fix_typing_runtime_module(func, result, scope)

    def eval_List(self, node: ast.List, scope: RuntimeScope) -> list:
        out: list[Any] = []
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.extend(self.eval_expr(elt.value, scope))
            else:
                out.append(self.eval_expr(elt, scope))
        return out

    def eval_Tuple(self, node: ast.Tuple, scope: RuntimeScope) -> tuple:
        out: list[Any] = []
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.extend(self.eval_expr(elt.value, scope))
            else:
                out.append(self.eval_expr(elt, scope))
        return tuple(out)

    def eval_Set(self, node: ast.Set, scope: RuntimeScope) -> set:
        out: set[Any] = set()
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.update(self.eval_expr(elt.value, scope))
            else:
                out.add(self.eval_expr(elt, scope))
        return out

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
            attr_name = self._mangle_private_name(node.attr, scope)
            guard_attr_name(attr_name)
            return getattr(obj, attr_name)
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

    def eval_FormattedValue(self, node: ast.FormattedValue, scope: RuntimeScope) -> str:
        value = self.eval_expr(node.value, scope)

        if node.conversion == 115:  # !s
            value = str(value)
        elif node.conversion == 114:  # !r
            value = repr(value)
        elif node.conversion == 97:  # !a
            value = ascii(value)
        elif node.conversion != -1:
            raise NotImplementedError(f"Unsupported f-string conversion {node.conversion!r}")

        if node.format_spec is not None:
            spec = self.eval_expr(node.format_spec, scope)
            return format(value, spec)
        return format(value, "")

    def eval_JoinedStr(self, node: ast.JoinedStr, scope: RuntimeScope) -> str:
        return "".join(str(self.eval_expr(part, scope)) for part in node.values)

    def eval_Interpolation(self, node: ast.AST, scope: RuntimeScope) -> Any:
        value = self.eval_expr(node.value, scope)
        format_spec = "" if node.format_spec is None else str(self.eval_expr(node.format_spec, scope))
        return self._build_template_interpolation(
            value,
            getattr(node, "str", ""),
            node.conversion,
            format_spec,
        )

    def eval_TemplateStr(self, node: ast.AST, scope: RuntimeScope) -> Any:
        if TemplateString is None:
            raise NotImplementedError("TemplateStr is not supported on this Python runtime")
        parts = [self.eval_expr(part, scope) for part in node.values]
        return TemplateString(*parts)

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

    def eval_Await(self, node: ast.Await, scope: RuntimeScope) -> Any:
        raise SyntaxError("'await' is only valid in async functions")

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

    def g_eval_NamedExpr(self, node: ast.NamedExpr, scope: RuntimeScope) -> Iterator[Any]:
        value = yield from self.g_eval_expr(node.value, scope)
        self._store_namedexpr_target(node.target, value, scope)
        return value

    def g_eval_Lambda(self, node: ast.Lambda, scope: RuntimeScope) -> Iterator[UserFunction]:
        defaults: list[Any] = []
        for default_node in node.args.defaults or []:
            defaults.append((yield from self.g_eval_expr(default_node, scope)))
        kw_defaults: list[Any] = []
        for default_node in getattr(node.args, "kw_defaults", []) or []:
            kw_defaults.append(
                (yield from self.g_eval_expr(default_node, scope))
                if default_node is not None
                else NO_DEFAULT
            )
        lambda_table = scope.code.lookup_lambda_table(node)
        lambda_scope_info = scope.code.scope_info_for(lambda_table)
        closure = {name: scope.capture_cell(name) for name in lambda_scope_info.frees}
        return UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            builtins_dict=scope.builtins,
            scope_info=lambda_scope_info,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=False,
            qualname=self._qualname_for_definition("<lambda>", scope),
            private_owner=getattr(scope, "private_owner", None),
        )

    def g_eval_Call(self, node: ast.Call, scope: RuntimeScope) -> Iterator[Any]:
        func = yield from self.g_eval_expr(node.func, scope)
        args: list[Any] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                args.extend((yield from self.g_eval_expr(arg.value, scope)))
            else:
                args.append((yield from self.g_eval_expr(arg, scope)))
        kwargs: Dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None:
                mapping = yield from self.g_eval_expr(kw.value, scope)
                self._merge_keyword_mapping(func, kwargs, mapping)
            else:
                value = yield from self.g_eval_expr(kw.value, scope)
                self._store_keyword(func, kwargs, kw.arg, value)
        super_value = self._maybe_zero_arg_super(func, args, kwargs)
        if super_value is not _NO_SUPER:
            return super_value
        if kwargs:
            result = func(*args, **kwargs)
        else:
            result = func(*args)
        return self._maybe_fix_typing_runtime_module(func, result, scope)

    def g_eval_List(self, node: ast.List, scope: RuntimeScope) -> Iterator[list]:
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.extend((yield from self.g_eval_expr(elt.value, scope)))
            else:
                out.append((yield from self.g_eval_expr(elt, scope)))
        return out

    def g_eval_Tuple(self, node: ast.Tuple, scope: RuntimeScope) -> Iterator[tuple]:
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.extend((yield from self.g_eval_expr(elt.value, scope)))
            else:
                out.append((yield from self.g_eval_expr(elt, scope)))
        return tuple(out)

    def g_eval_Set(self, node: ast.Set, scope: RuntimeScope) -> Iterator[set]:
        out = set()
        for elt in node.elts:
            if isinstance(elt, ast.Starred):
                out.update((yield from self.g_eval_expr(elt.value, scope)))
            else:
                out.add((yield from self.g_eval_expr(elt, scope)))
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
        attr_name = self._mangle_private_name(node.attr, scope)
        guard_attr_name(attr_name)
        return getattr(obj, attr_name)

    def g_eval_Subscript(self, node: ast.Subscript, scope: RuntimeScope) -> Iterator[Any]:
        obj = yield from self.g_eval_expr(node.value, scope)
        idx = yield from self.g_eval_expr(node.slice, scope)
        return obj[idx]

    def g_eval_Slice(self, node: ast.Slice, scope: RuntimeScope) -> Iterator[slice]:
        lo = (yield from self.g_eval_expr(node.lower, scope)) if node.lower else None
        hi = (yield from self.g_eval_expr(node.upper, scope)) if node.upper else None
        st = (yield from self.g_eval_expr(node.step, scope)) if node.step else None
        return slice(lo, hi, st)

    def g_eval_FormattedValue(self, node: ast.FormattedValue, scope: RuntimeScope) -> Iterator[str]:
        value = yield from self.g_eval_expr(node.value, scope)

        if node.conversion == 115:  # !s
            value = str(value)
        elif node.conversion == 114:  # !r
            value = repr(value)
        elif node.conversion == 97:  # !a
            value = ascii(value)
        elif node.conversion != -1:
            raise NotImplementedError(f"Unsupported f-string conversion {node.conversion!r}")

        if node.format_spec is not None:
            spec = yield from self.g_eval_expr(node.format_spec, scope)
            return format(value, spec)
        return format(value, "")

    def g_eval_JoinedStr(self, node: ast.JoinedStr, scope: RuntimeScope) -> Iterator[str]:
        parts = []
        for part in node.values:
            parts.append(str((yield from self.g_eval_expr(part, scope))))
        return "".join(parts)

    def g_eval_Interpolation(self, node: ast.AST, scope: RuntimeScope) -> Iterator[Any]:
        value = yield from self.g_eval_expr(node.value, scope)
        format_spec = (
            "" if node.format_spec is None else str((yield from self.g_eval_expr(node.format_spec, scope)))
        )
        return self._build_template_interpolation(
            value,
            getattr(node, "str", ""),
            node.conversion,
            format_spec,
        )

    def g_eval_TemplateStr(self, node: ast.AST, scope: RuntimeScope) -> Iterator[Any]:
        if TemplateString is None:
            raise NotImplementedError("TemplateStr is not supported on this Python runtime")
        parts = []
        for part in node.values:
            parts.append((yield from self.g_eval_expr(part, scope)))
        return TemplateString(*parts)

    # comprehensions (generator-mode)
    def _g_for_each_comprehension_item(
        self,
        gen: ast.comprehension,
        iterable: Any,
        on_item: Callable[[Any], Iterator[Any]],
    ) -> Iterator[Any]:
        if not getattr(gen, "is_async", False):
            for item in iterable:
                yield from on_item(item)
            return

        iterator = self._async_for_iter(iterable)
        while True:
            try:
                next_awaitable, raw_next, invalid_message = self._async_for_next_awaitable(iterator)
            except StopAsyncIteration:
                break

            try:
                item = yield AwaitRequest(next_awaitable)
            except StopAsyncIteration:
                break
            except BaseException as exc:
                # Keep coroutine exceptions intact but wrap invalid custom awaitables.
                if not (hasattr(raw_next, "send") and hasattr(raw_next, "throw")):
                    raise TypeError(invalid_message) from exc
                raise

            yield from on_item(item)

    def g_eval_ListComp(self, node: ast.ListComp, scope: RuntimeScope) -> Iterator[list]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

        out: list = []
        gens = node.generators
        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                val = yield from self.g_eval_expr(node.elt, comp_scope)
                out.append(val)
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))

            def on_item(item: Any) -> Iterator[Any]:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

            yield from self._g_for_each_comprehension_item(g, it, on_item)

        yield from rec(0)
        return out

    def g_eval_SetComp(self, node: ast.SetComp, scope: RuntimeScope) -> Iterator[set]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

        out: set = set()
        gens = node.generators
        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                val = yield from self.g_eval_expr(node.elt, comp_scope)
                out.add(val)
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))

            def on_item(item: Any) -> Iterator[Any]:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

            yield from self._g_for_each_comprehension_item(g, it, on_item)

        yield from rec(0)
        return out

    def g_eval_DictComp(self, node: ast.DictComp, scope: RuntimeScope) -> Iterator[dict]:
        locals_set = _collect_comprehension_locals(node.generators)
        comp_scope = ComprehensionScope(
            scope.code, scope.globals, scope.builtins, outer_scope=scope, local_names=locals_set
        )

        out: dict = {}
        gens = node.generators
        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        def rec(i: int) -> Iterator[Any]:
            if i == len(gens):
                k = yield from self.g_eval_expr(node.key, comp_scope)
                v = yield from self.g_eval_expr(node.value, comp_scope)
                out[k] = v
                return
            g = gens[i]
            it = outer_iter if i == 0 else (yield from self.g_eval_expr(g.iter, comp_scope))

            def on_item(item: Any) -> Iterator[Any]:
                yield from self.g_assign_target(g.target, item, comp_scope)
                ok = True
                for if_ in g.ifs:
                    cond = yield from self.g_eval_expr(if_, comp_scope)
                    if not cond:
                        ok = False
                        break
                if ok:
                    yield from rec(i + 1)

            yield from self._g_for_each_comprehension_item(g, it, on_item)

        yield from rec(0)
        return out

    def _expr_requires_await_during_eval(self, expr: ast.AST | None) -> bool:
        if expr is None:
            return False
        if isinstance(expr, ast.Await):
            return True
        if isinstance(expr, (ast.ListComp, ast.SetComp, ast.DictComp)):
            if any(getattr(gen, "is_async", False) for gen in expr.generators):
                return True
        # Nested generator expressions don't consume async iterators at creation
        # time, so they don't force the containing generator expression to become
        # an async iterator.
        if isinstance(expr, ast.GeneratorExp):
            return False
        return any(
            self._expr_requires_await_during_eval(child) for child in ast.iter_child_nodes(expr)
        )

    def _generator_exp_requires_async_iterator(self, node: ast.GeneratorExp) -> bool:
        if any(getattr(gen, "is_async", False) for gen in node.generators):
            return True
        if self._expr_requires_await_during_eval(node.elt):
            return True
        for gen in node.generators:
            if self._expr_requires_await_during_eval(gen.iter):
                return True
            for condition in gen.ifs:
                if self._expr_requires_await_during_eval(condition):
                    return True
        return False

    def g_eval_GeneratorExp(
        self, node: ast.GeneratorExp, scope: RuntimeScope
    ) -> Iterator[Any]:
        locals_set = _collect_comprehension_locals(node.generators)
        gens = node.generators
        has_async = self._generator_exp_requires_async_iterator(node)

        outer_iter = yield from self.g_eval_expr(gens[0].iter, scope)

        if has_async:

            def make_async_gen() -> Iterator[Any]:
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

                    def on_item(item: Any) -> Iterator[Any]:
                        yield from self.g_assign_target(g.target, item, comp_scope)
                        ok = True
                        for if_ in g.ifs:
                            cond = yield from self.g_eval_expr(if_, comp_scope)
                            if not cond:
                                ok = False
                                break
                        if ok:
                            yield from rec(i + 1)

                    yield from self._g_for_each_comprehension_item(g, it, on_item)

                yield from rec(0)

            return InterpretedAsyncGenerator(make_async_gen())

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
    def g_eval_Await(self, node: ast.Await, scope: RuntimeScope) -> Iterator[Any]:
        awaitable = yield from self.g_eval_expr(node.value, scope)
        if not hasattr(awaitable, "__await__"):
            raise TypeError(
                f"object {type(awaitable).__name__} can't be used in 'await' expression"
            )
        result = yield AwaitRequest(awaitable)
        return result

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
