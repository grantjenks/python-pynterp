from __future__ import annotations

import ast
from typing import Any, Dict, Iterator

from .common import NO_DEFAULT, BreakSignal, Cell, ContinueSignal, ControlFlowSignal, ReturnSignal
from .functions import UserFunction
from .scopes import ClassBodyScope, RuntimeScope
from .symtable_utils import _contains_yield


class StatementMixin:
    def exec_Expr(self, node: ast.Expr, scope: RuntimeScope) -> None:
        self.eval_expr(node.value, scope)

    def exec_Pass(self, node: ast.Pass, scope: RuntimeScope) -> None:
        return

    def exec_Assert(self, node: ast.Assert, scope: RuntimeScope) -> None:
        if self.eval_expr(node.test, scope):
            return
        if node.msg is None:
            raise AssertionError
        raise AssertionError(self.eval_expr(node.msg, scope))

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
            (self.eval_expr(d, scope) if d is not None else NO_DEFAULT)
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
            builtins_dict=scope.builtins,
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
        class_cell = Cell()

        body_scope = ClassBodyScope(
            scope.code,
            scope.globals,
            scope.builtins,
            outer_scope=scope,
            class_ns=class_ns,
            class_cell=class_cell,
        )
        self.exec_block(node.body, body_scope)

        cls = meta(node.name, tuple(bases), class_ns, **kw)
        class_cell.value = cls

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
                    names = [
                        k for k in getattr(mod, "__dict__", {}).keys() if not k.startswith("_")
                    ]
                for k in names:
                    scope.store(k, getattr(mod, k))
            else:
                scope.store(alias.asname or alias.name, getattr(mod, alias.name))

    # ----------------------------
    # Expressions (normal)

    def g_exec_Expr(self, node: ast.Expr, scope: RuntimeScope) -> Iterator[Any]:
        yield from self.g_eval_expr(node.value, scope)
        return

    def g_exec_Assign(self, node: ast.Assign, scope: RuntimeScope) -> Iterator[Any]:
        val = yield from self.g_eval_expr(node.value, scope)
        for tgt in node.targets:
            yield from self.g_assign_target(tgt, val, scope)
        return

    def g_exec_Assert(self, node: ast.Assert, scope: RuntimeScope) -> Iterator[Any]:
        test = yield from self.g_eval_expr(node.test, scope)
        if test:
            return
        if node.msg is None:
            raise AssertionError
        msg = yield from self.g_eval_expr(node.msg, scope)
        raise AssertionError(msg)

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
        for d in node.args.defaults or []:
            defaults.append((yield from self.g_eval_expr(d, scope)))
        kw_defaults = []
        for d in getattr(node.args, "kw_defaults", []) or []:
            kw_defaults.append(
                (yield from self.g_eval_expr(d, scope)) if d is not None else NO_DEFAULT
            )

        fn_table = scope.code.lookup_function_table(node)
        fn_scope_info = scope.code.scope_info_for(fn_table)
        closure = {name: scope.capture_cell(name) for name in fn_scope_info.frees}
        is_gen = _contains_yield(node)

        func = UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            builtins_dict=scope.builtins,
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
                kw[k.arg] = yield from self.g_eval_expr(k.value, scope)

        meta = kw.pop("metaclass", None)
        if meta is None:
            meta = type(bases[0]) if bases else type

        class_ns: Dict[str, Any] = {}
        class_ns.setdefault("__module__", scope.globals.get("__name__", "__main__"))
        class_ns.setdefault("__qualname__", node.name)
        class_cell = Cell()

        body_scope = ClassBodyScope(
            scope.code,
            scope.globals,
            scope.builtins,
            outer_scope=scope,
            class_ns=class_ns,
            class_cell=class_cell,
        )
        # class body itself cannot yield (syntax), so normal exec is OK:
        self.exec_block(node.body, body_scope)

        cls = meta(node.name, tuple(bases), class_ns, **kw)
        class_cell.value = cls

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
