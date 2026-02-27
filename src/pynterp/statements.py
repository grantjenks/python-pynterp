from __future__ import annotations

import ast
import builtins as py_builtins
import types as py_types
import typing as py_typing
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterator

from .common import (
    NO_DEFAULT,
    UNBOUND,
    AwaitRequest,
    BreakSignal,
    Cell,
    ContinueSignal,
    ControlFlowSignal,
    ReturnSignal,
)
from .functions import UserFunction
from .scopes import ClassBodyScope, FunctionScope, RuntimeScope
from .symtable_utils import _contains_yield

_MISSING = object()
_BUILTIN_MATCH_SELF_TYPES = (
    bool,
    bytearray,
    bytes,
    dict,
    float,
    frozenset,
    int,
    list,
    set,
    str,
    tuple,
)


class _TypeAliasEvalScope(RuntimeScope):
    def __init__(self, base_scope: RuntimeScope, type_param_bindings: Dict[str, Any]):
        super().__init__(
            base_scope.code,
            base_scope.globals,
            base_scope.builtins,
            private_owner=getattr(base_scope, "private_owner", None),
        )
        self._base_scope = base_scope
        self._type_param_bindings = type_param_bindings
        self._type_param_cells = {
            name: Cell(value) for name, value in type_param_bindings.items()
        }

    def load(self, name: str) -> Any:
        type_param_cell = self._type_param_cells.get(name)
        if type_param_cell is not None:
            if type_param_cell.value is UNBOUND:
                raise NameError(name)
            return type_param_cell.value
        return self._base_scope.load(name)

    def store(self, name: str, value: Any) -> Any:
        type_param_cell = self._type_param_cells.get(name)
        if type_param_cell is not None:
            type_param_cell.value = value
            self._type_param_bindings[name] = value
            return value
        return self._base_scope.store(name, value)

    def unbind(self, name: str) -> None:
        type_param_cell = self._type_param_cells.get(name)
        if type_param_cell is not None:
            type_param_cell.value = UNBOUND
            self._type_param_bindings.pop(name, None)
            return
        self._base_scope.unbind(name)

    def delete(self, name: str) -> None:
        type_param_cell = self._type_param_cells.get(name)
        if type_param_cell is not None:
            type_param_cell.value = UNBOUND
            self._type_param_bindings.pop(name, None)
            return
        self._base_scope.delete(name)

    def capture_cell(self, name: str) -> Cell:
        type_param_cell = self._type_param_cells.get(name)
        if type_param_cell is not None:
            return type_param_cell
        return self._base_scope.capture_cell(name)


class _AsyncForAwaitable:
    def __init__(self, iterator: Iterator[Any]):
        self._iterator = iterator

    def __await__(self) -> Iterator[Any]:
        return self._iterator


class StatementMixin:
    def _store_definition_name(self, scope: RuntimeScope, name: str, value: Any) -> None:
        scope.store(
            self._mangle_private_name_for_owner(name, getattr(scope, "private_owner", None)),
            value,
        )

    def _mangle_private_name_for_owner(self, name: str, private_owner: str | None) -> str:
        if not private_owner or not isinstance(name, str):
            return name
        if not name.startswith("__") or name.endswith("__") or "." in name:
            return name
        owner = private_owner.lstrip("_")
        if not owner:
            return name
        return f"_{owner}{name}"

    def _type_param_binding_names(
        self, name: str, *, private_owner: str | None
    ) -> tuple[str, ...]:
        names = [name]
        mangled_name = self._mangle_private_name_for_owner(name, private_owner)
        if mangled_name != name:
            names.append(mangled_name)
        return tuple(names)

    def _build_type_param_binding_map(
        self,
        type_param_nodes: Sequence[ast.AST],
        type_params: Sequence[Any],
        *,
        private_owner: str | None,
    ) -> Dict[str, Any]:
        bindings: Dict[str, Any] = {}
        for type_param_node, type_param in zip(type_param_nodes, type_params):
            for binding_name in self._type_param_binding_names(
                type_param_node.name,
                private_owner=private_owner,
            ):
                bindings[binding_name] = type_param
        return bindings

    def _build_type_param_cell_map(
        self,
        type_param_nodes: Sequence[ast.AST],
        type_params: Sequence[Any],
        *,
        private_owner: str | None,
    ) -> Dict[str, Cell]:
        cells: Dict[str, Cell] = {}
        for type_param_node, type_param in zip(type_param_nodes, type_params):
            type_param_cell = Cell(type_param)
            for binding_name in self._type_param_binding_names(
                type_param_node.name,
                private_owner=private_owner,
            ):
                cells[binding_name] = type_param_cell
        return cells

    def _new_provisional_type_param(self, node: ast.AST, scope: RuntimeScope) -> Any:
        if isinstance(node, ast.TypeVar):
            return self._typing_runtime_call(scope, py_typing.TypeVar, node.name)
        if isinstance(node, ast.ParamSpec):
            return self._typing_runtime_call(scope, py_typing.ParamSpec, node.name)
        if isinstance(node, ast.TypeVarTuple):
            return self._typing_runtime_call(scope, py_typing.TypeVarTuple, node.name)
        raise NotImplementedError(f"Type parameter not supported: {node.__class__.__name__}")

    def _eval_type_param_default(
        self, node: ast.expr, scope: RuntimeScope
    ) -> Any:
        if isinstance(node, ast.Starred):
            # Match compiler semantics for type-parameter defaults like `*Ts = *default`.
            (value,) = self.eval_expr(node.value, scope)
            return value
        return self.eval_expr(node, scope)

    def _typing_runtime_call(self, scope: RuntimeScope, factory: Any, /, *args: Any, **kwargs: Any) -> Any:
        # Run typing factories under interpreted globals so `__module__` matches the interpreted module.
        return eval(
            "__pynterp_factory(*__pynterp_args, **__pynterp_kwargs)",
            scope.globals,
            {
                "__pynterp_factory": factory,
                "__pynterp_args": args,
                "__pynterp_kwargs": kwargs,
            },
        )

    def _eval_class_bases(self, base_nodes: Sequence[ast.expr], scope: RuntimeScope) -> tuple[Any, ...]:
        bases: list[Any] = []
        for base_node in base_nodes:
            if isinstance(base_node, ast.Starred):
                bases.extend(self.eval_expr(base_node.value, scope))
            else:
                bases.append(self.eval_expr(base_node, scope))
        return tuple(bases)

    def _g_eval_class_bases(
        self, base_nodes: Sequence[ast.expr], scope: RuntimeScope
    ) -> Iterator[tuple[Any, ...]]:
        bases: list[Any] = []
        for base_node in base_nodes:
            if isinstance(base_node, ast.Starred):
                bases.extend((yield from self.g_eval_expr(base_node.value, scope)))
            else:
                bases.append((yield from self.g_eval_expr(base_node, scope)))
        return tuple(bases)

    def _generic_base_for_type_params(self, type_params: tuple[Any, ...]) -> Any:
        generic_params: list[Any] = []
        for type_param in type_params:
            if isinstance(type_param, py_typing.TypeVarTuple):
                generic_params.append(next(iter(type_param)))
            else:
                generic_params.append(type_param)
        return py_typing.Generic[tuple(generic_params)]

    def _coerce_raised_exception(self, exc: Any) -> BaseException:
        if isinstance(exc, BaseException):
            return exc
        if isinstance(exc, type) and issubclass(exc, BaseException):
            return exc()
        raise TypeError("Can only raise exception instances or exception classes")

    def _coerce_raise_cause(self, cause: Any) -> BaseException | None:
        if cause is None:
            return None
        if isinstance(cause, BaseException):
            return cause
        if isinstance(cause, type) and issubclass(cause, BaseException):
            return cause()
        raise TypeError("exception causes must derive from BaseException")

    def _raise_with_optional_cause(self, exc: Any, cause: Any = _MISSING) -> None:
        raise_exc = self._coerce_raised_exception(exc)
        if cause is _MISSING:
            raise raise_exc
        raise_cause = self._coerce_raise_cause(cause)
        if raise_cause is None:
            raise raise_exc from None
        raise raise_exc from raise_cause

    def _build_type_param(
        self, node: ast.AST, scope: RuntimeScope, type_param_bindings: Dict[str, Any]
    ) -> Any:
        eval_bindings = dict(type_param_bindings)
        private_owner = getattr(scope, "private_owner", None)
        if hasattr(node, "name"):
            provisional = self._new_provisional_type_param(node, scope)
            for binding_name in self._type_param_binding_names(
                node.name,
                private_owner=private_owner,
            ):
                eval_bindings.setdefault(binding_name, provisional)
        eval_scope = _TypeAliasEvalScope(scope, eval_bindings)

        if isinstance(node, ast.TypeVar):
            def build_lazy_typevar(
                *,
                bound_evaluator: Any = _MISSING,
                constraint_evaluators: tuple[Any, ...] = (),
                default_evaluator: Any = _MISSING,
            ) -> Any:
                params: list[str] = []
                args: list[Any] = []

                annotation = ""
                if bound_evaluator is not _MISSING:
                    params.append("__pynterp_eval_bound")
                    args.append(bound_evaluator)
                    annotation = ": __pynterp_eval_bound()"
                elif constraint_evaluators:
                    callback_names = []
                    for index, evaluator in enumerate(constraint_evaluators):
                        callback_name = f"__pynterp_eval_constraint_{index}"
                        params.append(callback_name)
                        args.append(evaluator)
                        callback_names.append(f"{callback_name}()")
                    tuple_expr = ", ".join(callback_names)
                    if len(callback_names) == 1:
                        tuple_expr += ","
                    annotation = f": ({tuple_expr})"

                default_expr = ""
                if default_evaluator is not _MISSING:
                    params.append("__pynterp_eval_default")
                    args.append(default_evaluator)
                    default_expr = " = __pynterp_eval_default()"

                param_list = ", ".join(params)
                module_name = scope.globals.get("__name__", "__main__")
                helper_globals: Dict[str, Any] = {
                    "__builtins__": scope.builtins,
                    "__name__": module_name if isinstance(module_name, str) else "__main__",
                }
                source = (
                    f"def __pynterp_make_typevar({param_list}):\n"
                    f"    def __pynterp_tmp[{node.name}{annotation}{default_expr}]():\n"
                    "        pass\n"
                    "    return __pynterp_tmp.__type_params__[0]\n"
                )
                exec(source, helper_globals)
                return helper_globals["__pynterp_make_typevar"](*args)

            kwargs: Dict[str, Any] = {}
            if node.default_value is not None:
                default_node = node.default_value
                default_evaluator = lambda: self._eval_type_param_default(default_node, eval_scope)
            else:
                default_evaluator = _MISSING
            if node.bound is None:
                if default_evaluator is _MISSING:
                    return self._typing_runtime_call(scope, py_typing.TypeVar, node.name, **kwargs)
                kwargs["default"] = default_evaluator()
                return self._typing_runtime_call(scope, py_typing.TypeVar, node.name, **kwargs)
            if isinstance(node.bound, ast.Tuple):
                try:
                    constraints = tuple(self.eval_expr(elt, eval_scope) for elt in node.bound.elts)
                except NameError:
                    lazy_bindings = dict(eval_bindings)
                    lazy_default_evaluator = (
                        (
                            lambda: self._eval_type_param_default(
                                default_node,
                                _TypeAliasEvalScope(scope, lazy_bindings),
                            )
                        )
                        if node.default_value is not None
                        else _MISSING
                    )
                    lazy_typevar = build_lazy_typevar(
                        constraint_evaluators=tuple(
                            (
                                lambda elt=elt: self.eval_expr(
                                    elt,
                                    _TypeAliasEvalScope(scope, lazy_bindings),
                                )
                            )
                            for elt in node.bound.elts
                        ),
                        default_evaluator=lazy_default_evaluator,
                    )
                    for binding_name in self._type_param_binding_names(
                        node.name,
                        private_owner=private_owner,
                    ):
                        lazy_bindings[binding_name] = lazy_typevar
                    return lazy_typevar
                if default_evaluator is not _MISSING:
                    kwargs["default"] = default_evaluator()
                return self._typing_runtime_call(
                    scope, py_typing.TypeVar, node.name, *constraints, **kwargs
                )
            try:
                kwargs["bound"] = self.eval_expr(node.bound, eval_scope)
            except NameError:
                lazy_bindings = dict(eval_bindings)
                lazy_default_evaluator = (
                    (
                        lambda: self._eval_type_param_default(
                            default_node,
                            _TypeAliasEvalScope(scope, lazy_bindings),
                        )
                    )
                    if node.default_value is not None
                    else _MISSING
                )
                lazy_typevar = build_lazy_typevar(
                    bound_evaluator=lambda: self.eval_expr(
                        node.bound,
                        _TypeAliasEvalScope(scope, lazy_bindings),
                    ),
                    default_evaluator=lazy_default_evaluator,
                )
                for binding_name in self._type_param_binding_names(
                    node.name,
                    private_owner=private_owner,
                ):
                    lazy_bindings[binding_name] = lazy_typevar
                return lazy_typevar
            if default_evaluator is not _MISSING:
                kwargs["default"] = default_evaluator()
            return self._typing_runtime_call(scope, py_typing.TypeVar, node.name, **kwargs)

        if isinstance(node, ast.ParamSpec):
            kwargs: Dict[str, Any] = {}
            if node.default_value is not None:
                kwargs["default"] = self._eval_type_param_default(node.default_value, eval_scope)
            return self._typing_runtime_call(scope, py_typing.ParamSpec, node.name, **kwargs)

        if isinstance(node, ast.TypeVarTuple):
            kwargs: Dict[str, Any] = {}
            if node.default_value is not None:
                kwargs["default"] = self._eval_type_param_default(node.default_value, eval_scope)
            return self._typing_runtime_call(scope, py_typing.TypeVarTuple, node.name, **kwargs)

        raise NotImplementedError(f"Type parameter not supported: {node.__class__.__name__}")

    def _build_type_params(self, nodes: Sequence[ast.AST], scope: RuntimeScope) -> tuple[Any, ...]:
        type_param_bindings: Dict[str, Any] = {}
        type_params: list[Any] = []
        private_owner = getattr(scope, "private_owner", None)
        for type_param_node in nodes:
            type_param = self._build_type_param(type_param_node, scope, type_param_bindings)
            for binding_name in self._type_param_binding_names(
                type_param_node.name,
                private_owner=private_owner,
            ):
                type_param_bindings[binding_name] = type_param
            type_params.append(type_param)
        return tuple(type_params)

    def _build_function_annotations(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: RuntimeScope,
        type_param_bindings: Dict[str, Any],
    ) -> Dict[str, Any]:
        annotations: Dict[str, Any] = {}
        eval_scope = _TypeAliasEvalScope(scope, type_param_bindings)
        args = node.args

        for arg in (*args.posonlyargs, *args.args):
            if arg.annotation is not None:
                annotations[arg.arg] = self.eval_expr(arg.annotation, eval_scope)

        if args.vararg is not None and args.vararg.annotation is not None:
            annotations[args.vararg.arg] = self.eval_expr(args.vararg.annotation, eval_scope)

        for arg in args.kwonlyargs:
            if arg.annotation is not None:
                annotations[arg.arg] = self.eval_expr(arg.annotation, eval_scope)

        if args.kwarg is not None and args.kwarg.annotation is not None:
            annotations[args.kwarg.arg] = self.eval_expr(args.kwarg.annotation, eval_scope)

        if node.returns is not None:
            annotations["return"] = self.eval_expr(node.returns, eval_scope)

        return annotations

    def _normalize_class_namespace(self, class_ns: Dict[str, Any]) -> None:
        # CPython implicitly wraps these hooks as classmethod when they are plain functions.
        for name in ("__init_subclass__", "__class_getitem__"):
            value = class_ns.get(name, _MISSING)
            if isinstance(value, UserFunction):
                class_ns[name] = py_builtins.classmethod(value)

    def exec_TypeAlias(self, node: ast.TypeAlias, scope: RuntimeScope) -> None:
        if not isinstance(node.name, ast.Name):
            raise NotImplementedError(
                f"TypeAlias target not supported: {node.name.__class__.__name__}"
            )

        type_params = self._build_type_params(node.type_params, scope)

        type_param_bindings = self._build_type_param_binding_map(
            node.type_params,
            type_params,
            private_owner=getattr(scope, "private_owner", None),
        )
        alias_eval_scope = _TypeAliasEvalScope(scope, type_param_bindings)
        alias_value = self.eval_expr(node.value, alias_eval_scope)
        alias = self._typing_runtime_call(
            scope,
            py_typing.TypeAliasType,
            node.name.id,
            alias_value,
            type_params=type_params,
        )

        self._store_definition_name(scope, node.name.id, alias)

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
        if node.value is not None:
            val = self.eval_expr(node.value, scope)
            self._assign_target(node.target, val, scope)

        # Function-local annotations are compile-time metadata only in CPython;
        # evaluating them at runtime raises spurious NameError for local hints.
        if isinstance(scope, FunctionScope):
            return

        if isinstance(node.target, ast.Name):
            ann = self.eval_expr(node.annotation, scope)
            ns = scope.class_ns if isinstance(scope, ClassBodyScope) else scope.globals
            anns = ns.get("__annotations__")
            if anns is None:
                anns = {}
                ns["__annotations__"] = anns
            anns[node.target.id] = ann

    def exec_AugAssign(self, node: ast.AugAssign, scope: RuntimeScope) -> None:
        old, store = self._resolve_augassign_target(node.target, scope)
        rhs = self.eval_expr(node.value, scope)
        store(self._apply_augop(node.op, old, rhs))

    def exec_If(self, node: ast.If, scope: RuntimeScope) -> None:
        if self.eval_expr(node.test, scope):
            self.exec_block(node.body, scope)
        else:
            self.exec_block(node.orelse, scope)

    def exec_Match(self, node: ast.Match, scope: RuntimeScope) -> None:
        subject = self.eval_expr(node.subject, scope)
        for case in node.cases:
            bindings: Dict[str, Any] = {}
            if not self._match_pattern(case.pattern, subject, scope, bindings):
                continue
            for name, value in bindings.items():
                scope.store(name, value)
            if case.guard is None or self.eval_expr(case.guard, scope):
                self.exec_block(case.body, scope)
                return

    def _merge_match_bindings(self, dst: Dict[str, Any], src: Dict[str, Any]) -> bool:
        for name, value in src.items():
            if name not in dst:
                dst[name] = value
                continue
            current = dst[name]
            if current is value:
                continue
            try:
                if current == value:
                    continue
            except BaseException:
                pass
            return False
        return True

    def _bind_match_name(self, bindings: Dict[str, Any], name: str, value: Any) -> bool:
        return self._merge_match_bindings(bindings, {name: value})

    def _match_pattern(
        self, pattern: ast.pattern, subject: Any, scope: RuntimeScope, bindings: Dict[str, Any]
    ) -> bool:
        if isinstance(pattern, ast.MatchValue):
            return subject == self.eval_expr(pattern.value, scope)

        if isinstance(pattern, ast.MatchSingleton):
            return subject is pattern.value

        if isinstance(pattern, ast.MatchSequence):
            return self._match_sequence_pattern(pattern, subject, scope, bindings)

        if isinstance(pattern, ast.MatchMapping):
            return self._match_mapping_pattern(pattern, subject, scope, bindings)

        if isinstance(pattern, ast.MatchClass):
            return self._match_class_pattern(pattern, subject, scope, bindings)

        if isinstance(pattern, ast.MatchAs):
            if pattern.pattern is not None:
                inner_bindings: Dict[str, Any] = {}
                if not self._match_pattern(pattern.pattern, subject, scope, inner_bindings):
                    return False
                if not self._merge_match_bindings(bindings, inner_bindings):
                    return False
            if pattern.name is not None:
                return self._bind_match_name(bindings, pattern.name, subject)
            return True

        if isinstance(pattern, ast.MatchOr):
            for subpattern in pattern.patterns:
                inner_bindings: Dict[str, Any] = {}
                if not self._match_pattern(subpattern, subject, scope, inner_bindings):
                    continue
                if not self._merge_match_bindings(bindings, inner_bindings):
                    return False
                return True
            return False

        raise NotImplementedError(f"Pattern not supported: {pattern.__class__.__name__}")

    def _match_sequence_pattern(
        self,
        pattern: ast.MatchSequence,
        subject: Any,
        scope: RuntimeScope,
        bindings: Dict[str, Any],
    ) -> bool:
        if isinstance(subject, Mapping):
            return False
        if isinstance(subject, (str, bytes, bytearray)):
            return False
        if not isinstance(subject, Sequence):
            return False

        items = list(subject)
        patterns = list(pattern.patterns)
        star_index = None
        for idx, subpattern in enumerate(patterns):
            if isinstance(subpattern, ast.MatchStar):
                star_index = idx
                break

        if star_index is None:
            if len(items) != len(patterns):
                return False
            for subpattern, item in zip(patterns, items):
                inner_bindings: Dict[str, Any] = {}
                if not self._match_pattern(subpattern, item, scope, inner_bindings):
                    return False
                if not self._merge_match_bindings(bindings, inner_bindings):
                    return False
            return True

        head_patterns = patterns[:star_index]
        tail_patterns = patterns[star_index + 1 :]
        if len(items) < len(head_patterns) + len(tail_patterns):
            return False

        for subpattern, item in zip(head_patterns, items):
            inner_bindings: Dict[str, Any] = {}
            if not self._match_pattern(subpattern, item, scope, inner_bindings):
                return False
            if not self._merge_match_bindings(bindings, inner_bindings):
                return False

        star_pattern = patterns[star_index]
        if not isinstance(star_pattern, ast.MatchStar):
            raise RuntimeError("internal error: expected MatchStar")
        star_count = len(items) - len(head_patterns) - len(tail_patterns)
        star_values = list(items[len(head_patterns) : len(head_patterns) + star_count])
        if star_pattern.name is not None and not self._bind_match_name(
            bindings, star_pattern.name, star_values
        ):
            return False

        if tail_patterns:
            tail_items = items[len(items) - len(tail_patterns) :]
            for subpattern, item in zip(tail_patterns, tail_items):
                inner_bindings = {}
                if not self._match_pattern(subpattern, item, scope, inner_bindings):
                    return False
                if not self._merge_match_bindings(bindings, inner_bindings):
                    return False

        return True

    def _match_mapping_pattern(
        self,
        pattern: ast.MatchMapping,
        subject: Any,
        scope: RuntimeScope,
        bindings: Dict[str, Any],
    ) -> bool:
        if not isinstance(subject, Mapping):
            return False

        keys: list[Any] = []
        for key_node in pattern.keys:
            keys.append(self.eval_expr(key_node, scope))

        for index, key in enumerate(keys):
            for previous in keys[:index]:
                if key == previous:
                    raise ValueError(f"mapping pattern checks duplicate key ({key!r})")

        matched_values: list[Any] = []
        for key in keys:
            if hasattr(subject, "get"):
                value = subject.get(key, _MISSING)
            else:
                try:
                    value = subject[key]
                except KeyError:
                    value = _MISSING
            if value is _MISSING:
                return False
            matched_values.append(value)

        for subpattern, value in zip(pattern.patterns, matched_values):
            inner_bindings: Dict[str, Any] = {}
            if not self._match_pattern(subpattern, value, scope, inner_bindings):
                return False
            if not self._merge_match_bindings(bindings, inner_bindings):
                return False

        if pattern.rest is not None:
            rest: Dict[Any, Any] = {}
            for key, value in subject.items():
                if any(key == matched_key for matched_key in keys):
                    continue
                rest[key] = value
            if not self._bind_match_name(bindings, pattern.rest, rest):
                return False
        return True

    def _match_class_pattern(
        self,
        pattern: ast.MatchClass,
        subject: Any,
        scope: RuntimeScope,
        bindings: Dict[str, Any],
    ) -> bool:
        cls = self.eval_expr(pattern.cls, scope)
        if not isinstance(cls, type):
            raise TypeError("called match pattern must be a type")
        if not isinstance(subject, cls):
            return False

        positional_patterns = list(pattern.patterns)
        keyword_attrs = list(pattern.kwd_attrs)
        keyword_patterns = list(pattern.kwd_patterns)
        positional_attrs: list[str] = []
        match_self = False

        if positional_patterns:
            match_args = getattr(cls, "__match_args__", _MISSING)
            if match_args is _MISSING:
                if cls in _BUILTIN_MATCH_SELF_TYPES:
                    match_self = True
                    match_args = ("__match_self__",)
                else:
                    match_args = ()
            if not isinstance(match_args, tuple):
                raise TypeError(f"{cls.__name__}.__match_args__ must be a tuple")
            if len(positional_patterns) > len(match_args):
                raise TypeError(
                    f"{cls.__name__}() accepts {len(match_args)} positional sub-patterns"
                )
            for attr in match_args[: len(positional_patterns)]:
                if not isinstance(attr, str):
                    raise TypeError(
                        f"{cls.__name__}.__match_args__ elements must be strings "
                        f"(got {type(attr).__name__})"
                    )
                positional_attrs.append(attr)

        seen_attrs = set()
        for attr in positional_attrs:
            if attr in seen_attrs:
                raise TypeError(f"{cls.__name__}() got multiple sub-patterns for {attr!r}")
            seen_attrs.add(attr)
        for attr in keyword_attrs:
            if attr in seen_attrs:
                raise TypeError(f"{cls.__name__}() got multiple sub-patterns for {attr!r}")
            seen_attrs.add(attr)

        for subpattern, attr in zip(positional_patterns, positional_attrs):
            if match_self and attr == "__match_self__":
                value = subject
            else:
                value = getattr(subject, attr, _MISSING)
                if value is _MISSING:
                    return False
            inner_bindings: Dict[str, Any] = {}
            if not self._match_pattern(subpattern, value, scope, inner_bindings):
                return False
            if not self._merge_match_bindings(bindings, inner_bindings):
                return False

        for attr, subpattern in zip(keyword_attrs, keyword_patterns):
            value = getattr(subject, attr, _MISSING)
            if value is _MISSING:
                return False
            inner_bindings: Dict[str, Any] = {}
            if not self._match_pattern(subpattern, value, scope, inner_bindings):
                return False
            if not self._merge_match_bindings(bindings, inner_bindings):
                return False

        return True

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

    def _async_for_iter(self, iterable: Any) -> Any:
        try:
            iterator = py_builtins.aiter(iterable)
        except TypeError as exc:
            raise TypeError(
                "'async for' requires an object with __aiter__ method, "
                f"got {type(iterable).__name__}"
            ) from exc

        if not hasattr(iterator, "__anext__"):
            raise TypeError(
                "'async for' received an object from __aiter__ "
                f"that does not implement __anext__: {type(iterator).__name__}"
            )

        return iterator

    def _async_for_next_awaitable(self, iterator: Any) -> tuple[Any, Any, str]:
        next_value = iterator.__anext__()
        message = (
            "'async for' received an invalid object from __anext__: "
            f"{type(next_value).__name__}"
        )

        await_method = getattr(next_value, "__await__", None)
        if await_method is None:
            raise TypeError(message)
        try:
            await_iter = iter(await_method())
        except BaseException as exc:
            raise TypeError(message) from exc

        return _AsyncForAwaitable(await_iter), next_value, message

    def _async_with_method(self, manager: Any, method_name: str) -> Any:
        method = getattr(manager, method_name, None)
        if method is None:
            manager_name = type(manager).__qualname__
            raise TypeError(
                f"'{manager_name}' object does not support the asynchronous context manager "
                f"protocol (missed {method_name} method)"
            )
        return method

    def _async_with_awaitable(self, value: Any, method_name: str) -> Any:
        message = (
            f"'async with' received an object from {method_name} "
            f"that does not implement __await__: {type(value).__name__}"
        )
        await_method = getattr(value, "__await__", None)
        if await_method is None:
            raise TypeError(message)
        try:
            await_iter = iter(await_method())
        except BaseException as exc:
            raise TypeError(message) from exc
        return _AsyncForAwaitable(await_iter)

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

    def _make_user_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: RuntimeScope,
        defaults: list[Any],
        kw_defaults: list[Any],
        *,
        is_async: bool,
    ) -> UserFunction:
        contains_yield = _contains_yield(node)

        fn_table = scope.code.lookup_function_table(node)
        fn_scope_info = scope.code.scope_info_for(fn_table)
        type_param_nodes = getattr(node, "type_params", ()) or ()
        type_params = self._build_type_params(type_param_nodes, scope)
        type_param_bindings = self._build_type_param_binding_map(
            type_param_nodes,
            type_params,
            private_owner=getattr(scope, "private_owner", None),
        )
        annotations = self._build_function_annotations(node, scope, type_param_bindings)
        closure: Dict[str, Cell] = {}
        for free_name in fn_scope_info.frees:
            type_param = type_param_bindings.get(free_name, _MISSING)
            if type_param is not _MISSING:
                closure[free_name] = Cell(type_param)
                continue
            closure[free_name] = scope.capture_cell(free_name)

        return UserFunction(
            interpreter=self,
            node=node,
            code=scope.code,
            globals_dict=scope.globals,
            builtins_dict=scope.builtins,
            scope_info=fn_scope_info,
            closure=closure,
            defaults=defaults,
            kw_defaults=kw_defaults,
            is_generator=(not is_async) and contains_yield,
            is_async=is_async,
            is_async_generator=is_async and contains_yield,
            qualname=self._qualname_for_definition(node.name, scope),
            type_params=type_params,
            annotations=annotations,
            private_owner=getattr(scope, "private_owner", None),
        )

    def exec_FunctionDef(self, node: ast.FunctionDef, scope: RuntimeScope) -> None:
        defaults = [self.eval_expr(d, scope) for d in (node.args.defaults or [])]
        kw_defaults = [
            (self.eval_expr(d, scope) if d is not None else NO_DEFAULT)
            for d in (getattr(node.args, "kw_defaults", []) or [])
        ]
        func = self._make_user_function(
            node,
            scope,
            defaults,
            kw_defaults,
            is_async=False,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = self.eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)

    def exec_AsyncFunctionDef(self, node: ast.AsyncFunctionDef, scope: RuntimeScope) -> None:
        defaults = [self.eval_expr(d, scope) for d in (node.args.defaults or [])]
        kw_defaults = [
            (self.eval_expr(d, scope) if d is not None else NO_DEFAULT)
            for d in (getattr(node.args, "kw_defaults", []) or [])
        ]
        func = self._make_user_function(
            node,
            scope,
            defaults,
            kw_defaults,
            is_async=True,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = self.eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)

    def exec_ClassDef(self, node: ast.ClassDef, scope: RuntimeScope) -> None:
        type_param_nodes = getattr(node, "type_params", ()) or ()
        type_params = self._build_type_params(type_param_nodes, scope)
        type_param_bindings = self._build_type_param_binding_map(
            type_param_nodes,
            type_params,
            private_owner=node.name,
        )
        type_param_cells = self._build_type_param_cell_map(
            type_param_nodes,
            type_params,
            private_owner=node.name,
        )
        eval_scope: RuntimeScope = (
            _TypeAliasEvalScope(scope, type_param_bindings) if type_param_bindings else scope
        )

        orig_bases = self._eval_class_bases(node.bases, eval_scope)
        if type_params:
            orig_bases = (*orig_bases, self._generic_base_for_type_params(type_params))
        bases = tuple(py_types.resolve_bases(orig_bases))
        kw: Dict[str, Any] = {}
        for k in node.keywords:
            if k.arg is None:
                kw.update(self.eval_expr(k.value, eval_scope))
            else:
                kw[k.arg] = self.eval_expr(k.value, eval_scope)

        meta = kw.pop("metaclass", None)
        if meta is None:
            meta = type(bases[0]) if bases else type

        class_ns: Dict[str, Any] = {}
        class_ns.setdefault("__module__", scope.globals.get("__name__", "__main__"))
        class_ns.setdefault("__qualname__", self._qualname_for_definition(node.name, scope))
        if type_params:
            class_ns.setdefault("__type_params__", type_params)
        if bases != orig_bases:
            class_ns.setdefault("__orig_bases__", orig_bases)
        class_cell = Cell()

        body_scope = ClassBodyScope(
            scope.code,
            scope.globals,
            scope.builtins,
            outer_scope=scope,
            class_ns=class_ns,
            class_cell=class_cell,
            type_param_cells=type_param_cells,
            private_owner=node.name,
        )
        self.exec_block(node.body, body_scope)
        self._normalize_class_namespace(class_ns)

        cls = meta(node.name, bases, class_ns, **kw)
        class_cell.value = cls

        decorated: Any = cls
        for dec_node in reversed(node.decorator_list or []):
            dec = self.eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)

    def _except_star_targets_exception_group(self, exc_type: Any) -> bool:
        if isinstance(exc_type, tuple):
            return any(self._except_star_targets_exception_group(item) for item in exc_type)
        if not isinstance(exc_type, type):
            return False
        try:
            return issubclass(exc_type, py_builtins.BaseExceptionGroup)
        except TypeError:
            return False

    def _raise_try_star_result(
        self,
        *,
        original: BaseException,
        original_was_group: bool,
        remaining: BaseException | None,
        raised: list[BaseException],
    ) -> None:
        if not raised and remaining is None:
            return

        if not raised:
            if original_was_group:
                if remaining is None:
                    return
                raise remaining
            raise original

        members: list[BaseException] = list(raised)
        if remaining is not None:
            members.append(remaining)

        if len(members) == 1:
            raise members[0]

        if all(isinstance(member, Exception) for member in members):
            raise py_builtins.ExceptionGroup(
                "",
                [member for member in members if isinstance(member, Exception)],
            )
        raise py_builtins.BaseExceptionGroup("", members)

    def exec_Try(self, node: ast.Try, scope: RuntimeScope) -> None:
        finalbody_exception = scope.active_exception
        try:
            self.exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise
            finalbody_exception = e
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
                    previous_exception = scope.active_exception
                    scope.active_exception = e
                    try:
                        self.exec_block(handler.body, scope)
                    except ControlFlowSignal:
                        # Returning/breaking/continuing from an except handler
                        # clears the in-flight exception before finally runs.
                        finalbody_exception = previous_exception
                        raise
                    except BaseException as handler_exc:
                        finalbody_exception = handler_exc
                        raise
                    else:
                        finalbody_exception = e
                    finally:
                        scope.active_exception = previous_exception
                        if handler.name:
                            scope.unbind(handler.name)
                    break
            if not handled:
                raise
        else:
            if node.orelse:
                try:
                    self.exec_block(node.orelse, scope)
                except BaseException as orelse_exc:
                    if not isinstance(orelse_exc, ControlFlowSignal):
                        finalbody_exception = orelse_exc
                    raise
        finally:
            if node.finalbody:
                previous_exception = scope.active_exception
                scope.active_exception = finalbody_exception
                try:
                    self.exec_block(node.finalbody, scope)
                finally:
                    scope.active_exception = previous_exception

    def exec_TryStar(self, node: ast.TryStar, scope: RuntimeScope) -> None:
        try:
            self.exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise

            if isinstance(e, py_builtins.BaseExceptionGroup):
                pending: BaseException | None = e
                original_was_group = True
            else:
                if isinstance(e, Exception):
                    pending = py_builtins.ExceptionGroup("", [e])
                else:
                    pending = py_builtins.BaseExceptionGroup("", [e])
                original_was_group = False

            raised: list[BaseException] = []
            for handler in node.handlers:
                if pending is None:
                    break
                if handler.type is None:
                    exc_type: Any = BaseException
                else:
                    exc_type = self.eval_expr(handler.type, scope)
                if self._except_star_targets_exception_group(exc_type):
                    raise TypeError(
                        "catching ExceptionGroup with except* is not allowed. Use except instead."
                    )
                matched, pending = pending.split(exc_type)
                if matched is None:
                    continue

                if handler.name:
                    scope.store(handler.name, matched)
                previous_exception = scope.active_exception
                scope.active_exception = matched
                try:
                    self.exec_block(handler.body, scope)
                except BaseException as new_e:
                    if isinstance(new_e, ControlFlowSignal):
                        raise
                    raised.append(new_e)
                finally:
                    scope.active_exception = previous_exception
                    if handler.name:
                        scope.unbind(handler.name)

            self._raise_try_star_result(
                original=e,
                original_was_group=original_was_group,
                remaining=pending,
                raised=raised,
            )

        else:
            if node.orelse:
                self.exec_block(node.orelse, scope)
        finally:
            if node.finalbody:
                self.exec_block(node.finalbody, scope)

    def exec_Raise(self, node: ast.Raise, scope: RuntimeScope) -> None:
        if node.exc is None:
            if scope.active_exception is None:
                raise RuntimeError("No active exception to reraise")
            raise scope.active_exception
        exc = self.eval_expr(node.exc, scope)
        if node.cause is None:
            self._raise_with_optional_cause(exc)
        cause = self.eval_expr(node.cause, scope)
        self._raise_with_optional_cause(exc, cause)

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

    def exec_AsyncWith(self, node: ast.AsyncWith, scope: RuntimeScope) -> None:
        raise SyntaxError("'async with' is only valid in async functions")

    def exec_Import(self, node: ast.Import, scope: RuntimeScope) -> None:
        for alias in node.names:
            fromlist: tuple[str, ...] = ()
            if alias.asname and "." in alias.name:
                # CPython binds "import pkg.mod as alias" to the leaf module,
                # not the top-level package object.
                fromlist = (alias.name.rsplit(".", 1)[-1],)

            mod = self._import(alias.name, scope, fromlist=fromlist, level=0)
            bind = alias.asname or alias.name.split(".", 1)[0]
            scope.store(bind, mod)

    def exec_ImportFrom(self, node: ast.ImportFrom, scope: RuntimeScope) -> None:
        if node.level and not self.allow_relative_imports:
            raise ImportError("relative imports are not supported by this interpreter")
        import_name = node.module or ""
        fromlist = [a.name for a in node.names if a.name != "*"]
        mod = self._import(import_name, scope, fromlist=fromlist or ("*",), level=node.level or 0)

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
        if isinstance(scope, FunctionScope):
            return
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
        old, store = yield from self.g_resolve_augassign_target(node.target, scope)
        rhs = yield from self.g_eval_expr(node.value, scope)
        store(self._apply_augop(node.op, old, rhs))
        return

    def g_exec_If(self, node: ast.If, scope: RuntimeScope) -> Iterator[Any]:
        test = yield from self.g_eval_expr(node.test, scope)
        if test:
            yield from self.g_exec_block(node.body, scope)
        else:
            yield from self.g_exec_block(node.orelse, scope)
        return

    def g_exec_Match(self, node: ast.Match, scope: RuntimeScope) -> Iterator[Any]:
        subject = yield from self.g_eval_expr(node.subject, scope)
        for case in node.cases:
            bindings: Dict[str, Any] = {}
            if not self._match_pattern(case.pattern, subject, scope, bindings):
                continue
            for name, value in bindings.items():
                scope.store(name, value)
            if case.guard is not None:
                guard = yield from self.g_eval_expr(case.guard, scope)
                if not guard:
                    continue
            yield from self.g_exec_block(case.body, scope)
            return
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

    def g_exec_AsyncFor(self, node: ast.AsyncFor, scope: RuntimeScope) -> Iterator[Any]:
        iterable = yield from self.g_eval_expr(node.iter, scope)
        iterator = self._async_for_iter(iterable)
        broke = False

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
                # Keep asyncio/coroutine exceptions intact but wrap invalid custom awaitables
                # with the async-for specific TypeError shape.
                if not (hasattr(raw_next, "send") and hasattr(raw_next, "throw")):
                    raise TypeError(invalid_message) from exc
                raise

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
        func = self._make_user_function(
            node,
            scope,
            defaults,
            kw_defaults,
            is_async=False,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = yield from self.g_eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)
        return

    def g_exec_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef, scope: RuntimeScope
    ) -> Iterator[Any]:
        defaults: list[Any] = []
        for d in node.args.defaults or []:
            defaults.append((yield from self.g_eval_expr(d, scope)))
        kw_defaults: list[Any] = []
        for d in getattr(node.args, "kw_defaults", []) or []:
            kw_defaults.append(
                (yield from self.g_eval_expr(d, scope)) if d is not None else NO_DEFAULT
            )
        func = self._make_user_function(
            node,
            scope,
            defaults,
            kw_defaults,
            is_async=True,
        )

        decorated: Any = func
        for dec_node in reversed(node.decorator_list or []):
            dec = yield from self.g_eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)
        return

    def g_exec_ClassDef(self, node: ast.ClassDef, scope: RuntimeScope) -> Iterator[Any]:
        type_param_nodes = getattr(node, "type_params", ()) or ()
        type_params = self._build_type_params(type_param_nodes, scope)
        type_param_bindings = self._build_type_param_binding_map(
            type_param_nodes,
            type_params,
            private_owner=node.name,
        )
        type_param_cells = self._build_type_param_cell_map(
            type_param_nodes,
            type_params,
            private_owner=node.name,
        )
        eval_scope: RuntimeScope = (
            _TypeAliasEvalScope(scope, type_param_bindings) if type_param_bindings else scope
        )

        orig_bases = yield from self._g_eval_class_bases(node.bases, eval_scope)
        if type_params:
            orig_bases = (*orig_bases, self._generic_base_for_type_params(type_params))
        bases = tuple(py_types.resolve_bases(orig_bases))
        kw: Dict[str, Any] = {}
        for k in node.keywords:
            if k.arg is None:
                kw.update((yield from self.g_eval_expr(k.value, eval_scope)))
            else:
                kw[k.arg] = yield from self.g_eval_expr(k.value, eval_scope)

        meta = kw.pop("metaclass", None)
        if meta is None:
            meta = type(bases[0]) if bases else type

        class_ns: Dict[str, Any] = {}
        class_ns.setdefault("__module__", scope.globals.get("__name__", "__main__"))
        class_ns.setdefault("__qualname__", self._qualname_for_definition(node.name, scope))
        if type_params:
            class_ns.setdefault("__type_params__", type_params)
        if bases != orig_bases:
            class_ns.setdefault("__orig_bases__", orig_bases)
        class_cell = Cell()

        body_scope = ClassBodyScope(
            scope.code,
            scope.globals,
            scope.builtins,
            outer_scope=scope,
            class_ns=class_ns,
            class_cell=class_cell,
            type_param_cells=type_param_cells,
            private_owner=node.name,
        )
        # class body itself cannot yield (syntax), so normal exec is OK:
        self.exec_block(node.body, body_scope)
        self._normalize_class_namespace(class_ns)

        cls = meta(node.name, bases, class_ns, **kw)
        class_cell.value = cls

        decorated: Any = cls
        for dec_node in reversed(node.decorator_list or []):
            dec = yield from self.g_eval_expr(dec_node, scope)
            decorated = dec(decorated)

        self._store_definition_name(scope, node.name, decorated)
        return

    def g_exec_Try(self, node: ast.Try, scope: RuntimeScope) -> Iterator[Any]:
        finalbody_exception = scope.active_exception
        try:
            yield from self.g_exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise
            finalbody_exception = e
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
                    previous_exception = scope.active_exception
                    scope.active_exception = e
                    try:
                        yield from self.g_exec_block(handler.body, scope)
                    except ControlFlowSignal:
                        # Returning/breaking/continuing from an except handler
                        # clears the in-flight exception before finally runs.
                        finalbody_exception = previous_exception
                        raise
                    except BaseException as handler_exc:
                        finalbody_exception = handler_exc
                        raise
                    else:
                        finalbody_exception = e
                    finally:
                        scope.active_exception = previous_exception
                        if handler.name:
                            scope.unbind(handler.name)
                    break
            if not handled:
                raise
        else:
            if node.orelse:
                try:
                    yield from self.g_exec_block(node.orelse, scope)
                except BaseException as orelse_exc:
                    if not isinstance(orelse_exc, ControlFlowSignal):
                        finalbody_exception = orelse_exc
                    raise
        finally:
            if node.finalbody:
                previous_exception = scope.active_exception
                scope.active_exception = finalbody_exception
                try:
                    yield from self.g_exec_block(node.finalbody, scope)
                finally:
                    scope.active_exception = previous_exception
        return

    def g_exec_TryStar(self, node: ast.TryStar, scope: RuntimeScope) -> Iterator[Any]:
        try:
            yield from self.g_exec_block(node.body, scope)
        except BaseException as e:
            if isinstance(e, ControlFlowSignal):
                raise

            if isinstance(e, py_builtins.BaseExceptionGroup):
                pending: BaseException | None = e
                original_was_group = True
            else:
                if isinstance(e, Exception):
                    pending = py_builtins.ExceptionGroup("", [e])
                else:
                    pending = py_builtins.BaseExceptionGroup("", [e])
                original_was_group = False

            raised: list[BaseException] = []
            for handler in node.handlers:
                if pending is None:
                    break
                if handler.type is None:
                    exc_type: Any = BaseException
                else:
                    exc_type = yield from self.g_eval_expr(handler.type, scope)
                if self._except_star_targets_exception_group(exc_type):
                    raise TypeError(
                        "catching ExceptionGroup with except* is not allowed. Use except instead."
                    )
                matched, pending = pending.split(exc_type)
                if matched is None:
                    continue

                if handler.name:
                    scope.store(handler.name, matched)
                previous_exception = scope.active_exception
                scope.active_exception = matched
                try:
                    yield from self.g_exec_block(handler.body, scope)
                except BaseException as new_e:
                    if isinstance(new_e, ControlFlowSignal):
                        raise
                    raised.append(new_e)
                finally:
                    scope.active_exception = previous_exception
                    if handler.name:
                        scope.unbind(handler.name)

            self._raise_try_star_result(
                original=e,
                original_was_group=original_was_group,
                remaining=pending,
                raised=raised,
            )
        else:
            if node.orelse:
                yield from self.g_exec_block(node.orelse, scope)
        finally:
            if node.finalbody:
                yield from self.g_exec_block(node.finalbody, scope)
        return

    def g_exec_Raise(self, node: ast.Raise, scope: RuntimeScope) -> Iterator[Any]:
        if node.exc is None:
            if scope.active_exception is None:
                raise RuntimeError("No active exception to reraise")
            raise scope.active_exception
        exc = yield from self.g_eval_expr(node.exc, scope)
        if node.cause is None:
            self._raise_with_optional_cause(exc)
        cause = yield from self.g_eval_expr(node.cause, scope)
        self._raise_with_optional_cause(exc, cause)

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

    def g_exec_AsyncWith(self, node: ast.AsyncWith, scope: RuntimeScope) -> Iterator[Any]:
        exits = []
        try:
            for item in node.items:
                mgr = yield from self.g_eval_expr(item.context_expr, scope)
                exit_ = self._async_with_method(mgr, "__aexit__")
                enter = self._async_with_method(mgr, "__aenter__")
                val = yield AwaitRequest(self._async_with_awaitable(enter(), "__aenter__"))
                exits.append(exit_)
                if item.optional_vars is not None:
                    yield from self.g_assign_target(item.optional_vars, val, scope)

            yield from self.g_exec_block(node.body, scope)

        except ControlFlowSignal:
            for exit_ in reversed(exits):
                yield AwaitRequest(
                    self._async_with_awaitable(exit_(None, None, None), "__aexit__")
                )
            raise

        except BaseException as e:
            exc_type = type(e)
            exc = e
            tb = e.__traceback__

            for exit_ in reversed(exits):
                try:
                    suppress = yield AwaitRequest(
                        self._async_with_awaitable(exit_(exc_type, exc, tb), "__aexit__")
                    )
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
                yield AwaitRequest(
                    self._async_with_awaitable(exit_(None, None, None), "__aexit__")
                )

        return

    def g_exec_Import(self, node: ast.Import, scope: RuntimeScope) -> Iterator[Any]:
        self.exec_Import(node, scope)
        return
        yield  # unreachable

    def g_exec_ImportFrom(self, node: ast.ImportFrom, scope: RuntimeScope) -> Iterator[Any]:
        self.exec_ImportFrom(node, scope)
        return
        yield

    def g_exec_TypeAlias(self, node: ast.TypeAlias, scope: RuntimeScope) -> Iterator[Any]:
        self.exec_TypeAlias(node, scope)
        return
        yield

    def g_exec_Global(self, node: ast.Global, scope: RuntimeScope) -> Iterator[Any]:
        return
        yield

    def g_exec_Nonlocal(self, node: ast.Nonlocal, scope: RuntimeScope) -> Iterator[Any]:
        return
        yield

    # Expressions (generator mode)
