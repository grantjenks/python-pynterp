from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Dict, Iterator

from .common import NO_DEFAULT, UNBOUND, AwaitRequest, ReturnSignal
from .functions import UserFunction
from .lib.guards import safe_delattr, safe_getattr, safe_setattr
from .scopes import ClassBodyScope, ComprehensionScope, FunctionScope, RuntimeScope

_PY_ANY = any
_PY_HASATTR = hasattr
_PY_ISINSTANCE = isinstance
_PY_LEN = len
_PY_NEXT = next
_PY_TUPLE = tuple
_PY_ZIP = zip


class InterpretedAsyncGenerator:
    def __init__(self, body_runner: Iterator[Any]):
        self._body_runner = body_runner
        self._started = False
        self._closed = False
        self._running = False

    def __aiter__(self) -> "InterpretedAsyncGenerator":
        return self

    async def __anext__(self) -> Any:
        return await self.asend(None)

    async def asend(self, value: Any) -> Any:
        return await self._resume(send_value=value)

    @staticmethod
    def _build_throw_exception(typ: Any, val: Any = NO_DEFAULT, tb: Any = None) -> BaseException:
        if isinstance(typ, BaseException):
            if val is not NO_DEFAULT:
                raise TypeError("instance exception may not have a separate value")
            if tb is not None:
                return typ.with_traceback(tb)
            return typ

        if not isinstance(typ, type) or not issubclass(typ, BaseException):
            raise TypeError("exceptions must be classes or instances deriving from BaseException")

        if val is NO_DEFAULT:
            exc = typ()
        elif isinstance(val, BaseException):
            exc = val
        else:
            exc = typ(val)
        if tb is not None:
            exc = exc.with_traceback(tb)
        return exc

    async def athrow(self, typ: Any, val: Any = NO_DEFAULT, tb: Any = None) -> Any:
        exc = self._build_throw_exception(typ, val, tb)
        return await self._resume(thrown=exc)

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            await self.athrow(GeneratorExit)
        except (GeneratorExit, StopAsyncIteration):
            self._closed = True
            return
        raise RuntimeError("async generator ignored GeneratorExit")

    async def _resume(self, *, send_value: Any = None, thrown: BaseException | None = None) -> Any:
        if self._closed:
            raise StopAsyncIteration
        if self._running:
            raise RuntimeError("async generator is already running")

        self._running = True
        try:
            if thrown is not None:
                produced = self._body_runner.throw(thrown)
                self._started = True
            elif not self._started:
                if send_value is not None:
                    raise TypeError("can't send non-None value to a just-started async generator")
                produced = next(self._body_runner)
                self._started = True
            else:
                produced = self._body_runner.send(send_value)

            while True:
                if isinstance(produced, AwaitRequest):
                    try:
                        resume = await produced.awaitable
                    except BaseException as exc:
                        produced = self._body_runner.throw(exc)
                    else:
                        produced = self._body_runner.send(resume)
                    continue
                return produced
        except StopAsyncIteration as exc:
            self._closed = True
            raise RuntimeError("async generator raised StopAsyncIteration") from exc
        except StopIteration:
            self._closed = True
            raise StopAsyncIteration
        finally:
            self._running = False


class HelperMixin:
    def _qualname_prefix_for_scope(self, scope: RuntimeScope) -> str:
        # Some runtime scopes proxy another scope (for example type-alias eval scopes).
        base_scope = getattr(scope, "_base_scope", None)
        if isinstance(base_scope, RuntimeScope):
            return self._qualname_prefix_for_scope(base_scope)

        if isinstance(scope, ComprehensionScope):
            return self._qualname_prefix_for_scope(scope.outer_scope)

        if isinstance(scope, ClassBodyScope):
            qualname = scope.class_ns.get("__qualname__", "")
            return qualname if isinstance(qualname, str) else ""

        if isinstance(scope, FunctionScope) and scope.qualname:
            return f"{scope.qualname}.<locals>"

        return ""

    def _qualname_for_definition(self, name: str, scope: RuntimeScope) -> str:
        prefix = self._qualname_prefix_for_scope(scope)
        if not prefix:
            return name
        return f"{prefix}.{name}"

    def _mangle_private_name(self, name: str, scope: RuntimeScope) -> str:
        owner = getattr(scope, "private_owner", None)
        if not owner or not isinstance(name, str):
            return name
        if not name.startswith("__") or name.endswith("__") or "." in name:
            return name
        owner = owner.lstrip("_")
        if not owner:
            return name
        return f"_{owner}{name}"

    def _unpack_sequence_target(self, target: ast.Tuple | ast.List, value: Any) -> list[tuple[ast.AST, Any]]:
        items = list(value)
        elts = list(target.elts)
        star_indexes = [index for index, elt in enumerate(elts) if isinstance(elt, ast.Starred)]

        if not star_indexes:
            expected = len(elts)
            got = len(items)
            if got < expected:
                raise ValueError(f"not enough values to unpack (expected {expected}, got {got})")
            if got > expected:
                raise ValueError(f"too many values to unpack (expected {expected})")
            return list(zip(elts, items))

        if len(star_indexes) > 1:
            raise ValueError("multiple starred assignment targets")

        star_index = star_indexes[0]
        head = elts[:star_index]
        tail = elts[star_index + 1 :]
        expected = len(head) + len(tail)
        got = len(items)
        if got < expected:
            raise ValueError(
                f"not enough values to unpack (expected at least {expected}, got {got})"
            )

        assignments: list[tuple[ast.AST, Any]] = []
        for elt, item in zip(head, items):
            assignments.append((elt, item))

        star_target = elts[star_index]
        if not isinstance(star_target, ast.Starred):
            raise RuntimeError("internal error: expected Starred target")
        star_count = got - expected
        star_values = items[len(head) : len(head) + star_count]
        assignments.append((star_target.value, star_values))

        tail_items = items[got - len(tail) :] if tail else []
        for elt, item in zip(tail, tail_items):
            assignments.append((elt, item))
        return assignments

    def _assign_target(self, target: ast.AST, value: Any, scope: RuntimeScope) -> None:
        if isinstance(target, ast.Name):
            scope.store(target.id, value)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt, item in self._unpack_sequence_target(target, value):
                self._assign_target(elt, item, scope)
            return
        if isinstance(target, ast.Starred):
            self._assign_target(target.value, value, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = self.eval_expr(target.value, scope)
            safe_setattr(obj, self._mangle_private_name(target.attr, scope), value)
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
            for elt, item in self._unpack_sequence_target(target, value):
                yield from self.g_assign_target(elt, item, scope)
            return
        if isinstance(target, ast.Starred):
            yield from self.g_assign_target(target.value, value, scope)
            return
        if isinstance(target, ast.Attribute):
            obj = yield from self.g_eval_expr(target.value, scope)
            safe_setattr(obj, self._mangle_private_name(target.attr, scope), value)
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
            safe_delattr(obj, self._mangle_private_name(target.attr, scope))
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
            safe_delattr(obj, self._mangle_private_name(target.attr, scope))
            return
        if isinstance(target, ast.Subscript):
            obj = yield from self.g_eval_expr(target.value, scope)
            idx = yield from self.g_eval_expr(target.slice, scope)
            del obj[idx]
            return
        raise NotImplementedError(f"del target not supported: {target.__class__.__name__}")

    def _resolve_augassign_target(
        self, target: ast.expr, scope: RuntimeScope
    ) -> tuple[Any, Callable[[Any], None]]:
        if isinstance(target, ast.Name):
            name = target.id
            old = scope.load(name)

            def store(value: Any) -> None:
                scope.store(name, value)

            return old, store

        if isinstance(target, ast.Attribute):
            obj = self.eval_expr(target.value, scope)
            attr_name = self._mangle_private_name(target.attr, scope)
            old = safe_getattr(obj, attr_name)

            def store(value: Any) -> None:
                safe_setattr(obj, attr_name, value)

            return old, store

        if isinstance(target, ast.Subscript):
            obj = self.eval_expr(target.value, scope)
            idx = (
                self.eval_expr(target.slice, scope)
                if not isinstance(target.slice, ast.Slice)
                else self._eval_slice(target.slice, scope)
            )
            old = obj[idx]

            def store(value: Any) -> None:
                obj[idx] = value

            return old, store

        raise NotImplementedError(f"AugAssign target not supported: {target.__class__.__name__}")

    def g_resolve_augassign_target(
        self, target: ast.expr, scope: RuntimeScope
    ) -> Iterator[tuple[Any, Callable[[Any], None]]]:
        if isinstance(target, ast.Name):
            name = target.id
            old = scope.load(name)

            def store(value: Any) -> None:
                scope.store(name, value)

            return old, store
            yield

        if isinstance(target, ast.Attribute):
            obj = yield from self.g_eval_expr(target.value, scope)
            attr_name = self._mangle_private_name(target.attr, scope)
            old = safe_getattr(obj, attr_name)

            def store(value: Any) -> None:
                safe_setattr(obj, attr_name, value)

            return old, store

        if isinstance(target, ast.Subscript):
            obj = yield from self.g_eval_expr(target.value, scope)
            idx = yield from self.g_eval_expr(target.slice, scope)
            old = obj[idx]

            def store(value: Any) -> None:
                obj[idx] = value

            return old, store

        raise NotImplementedError(f"AugAssign target not supported: {target.__class__.__name__}")

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

    def _apply_augop(self, op: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add):
            return operator.iadd(left, right)
        if isinstance(op, ast.Sub):
            return operator.isub(left, right)
        if isinstance(op, ast.Mult):
            return operator.imul(left, right)
        if isinstance(op, ast.Div):
            return operator.itruediv(left, right)
        if isinstance(op, ast.FloorDiv):
            return operator.ifloordiv(left, right)
        if isinstance(op, ast.Mod):
            return operator.imod(left, right)
        if isinstance(op, ast.Pow):
            return operator.ipow(left, right)
        if isinstance(op, ast.BitAnd):
            return operator.iand(left, right)
        if isinstance(op, ast.BitOr):
            return operator.ior(left, right)
        if isinstance(op, ast.BitXor):
            return operator.ixor(left, right)
        if isinstance(op, ast.LShift):
            return operator.ilshift(left, right)
        if isinstance(op, ast.RShift):
            return operator.irshift(left, right)
        if isinstance(op, ast.MatMult):
            return operator.imatmul(left, right)
        raise NotImplementedError(f"AugAssign op {op.__class__.__name__} not supported")

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
        func_name = getattr(node, "name", "<lambda>")
        call_scope = FunctionScope(
            func_obj.code,
            func_obj.globals,
            func_obj.builtins,
            si,
            func_obj.closure,
            qualname=func_obj.__qualname__,
            private_owner=func_obj._private_owner,
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
            for name, val in _PY_ZIP(params[-_PY_LEN(func_obj.defaults) :], func_obj.defaults):
                default_map[name] = val

        # positional binding
        if _PY_LEN(args) > _PY_LEN(params) and node.args.vararg is None:
            raise TypeError(
                f"{func_name}() takes {_PY_LEN(params)} positional args but {_PY_LEN(args)} were given"
            )

        for name, val in _PY_ZIP(params, args):
            call_scope.store(name, val)

        extra_pos = args[_PY_LEN(params) :]
        if extra_pos:
            if node.args.vararg is None:
                raise TypeError("varargs not supported")
            call_scope.store(node.args.vararg.arg, _PY_TUPLE(extra_pos))

        # keyword binding
        for k, v in kwargs.items():
            if k in params or k in kwonly_names:
                if _PY_ANY(k == a.arg for a in posonly):
                    raise TypeError(
                        f"{func_name}() got positional-only arg '{k}' passed as keyword"
                    )
                if is_bound(k):
                    raise TypeError(f"{func_name}() got multiple values for argument '{k}'")
                call_scope.store(k, v)
            else:
                if node.args.kwarg is None:
                    raise TypeError(f"{func_name}() got unexpected keyword argument '{k}'")
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
                    raise TypeError(f"{func_name}() missing required argument '{name}'")

        # kw-only
        if kwonlyargs:
            for arg_node, default_val in _PY_ZIP(kwonlyargs, func_obj.kw_defaults):
                name = arg_node.arg
                if not is_bound(name):
                    if default_val is not NO_DEFAULT:
                        call_scope.store(name, default_val)
                    else:
                        raise TypeError(
                            f"{func_name}() missing required keyword-only argument '{name}'"
                        )

        # ensure vararg/kwarg exist
        if node.args.vararg is not None and not is_bound(node.args.vararg.arg):
            call_scope.store(node.args.vararg.arg, ())
        if node.args.kwarg is not None and not is_bound(node.args.kwarg.arg):
            call_scope.store(node.args.kwarg.arg, {})

        if not _PY_HASATTR(self, "_call_stack"):
            self._call_stack = []
        frame = (func_obj, call_scope)

        if func_obj.is_async:
            if func_obj.is_async_generator:

                def async_gen_runner():
                    self._call_stack.append(frame)
                    try:
                        try:
                            yield from self.g_exec_block(node.body, call_scope)
                        except ReturnSignal:
                            return
                    finally:
                        self._call_stack.pop()

                return InterpretedAsyncGenerator(async_gen_runner())

            async def async_runner():
                self._call_stack.append(frame)
                try:
                    body_runner = self.g_exec_block(node.body, call_scope)
                    try:
                        yielded = _PY_NEXT(body_runner)
                    except StopIteration:
                        return None
                    except ReturnSignal as r:
                        return r.value

                    while True:
                        if not _PY_ISINSTANCE(yielded, AwaitRequest):
                            raise RuntimeError("internal error: unexpected async function yield value")
                        try:
                            resume = await yielded.awaitable
                        except BaseException as exc:
                            try:
                                yielded = body_runner.throw(exc)
                            except StopIteration:
                                return None
                            except ReturnSignal as r:
                                return r.value
                        else:
                            try:
                                yielded = body_runner.send(resume)
                            except StopIteration:
                                return None
                            except ReturnSignal as r:
                                return r.value
                finally:
                    self._call_stack.pop()

            return async_runner()

        # normal function executes immediately
        if not func_obj.is_generator:
            self._call_stack.append(frame)
            try:
                try:
                    if _PY_ISINSTANCE(node, ast.Lambda):
                        return self.eval_expr(node.body, call_scope)
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
