from __future__ import annotations

import ast
import copy
import importlib
import inspect
import weakref
from typing import TYPE_CHECKING, Any, Dict

from .code import ModuleCode, ScopeInfo
from .common import NO_DEFAULT, Cell

if TYPE_CHECKING:
    from .main import Interpreter


_USER_FUNCTION_INTERPRETERS = weakref.WeakKeyDictionary()


def _resolve_qualname_attr(obj: Any, qualname: str) -> Any:
    current = obj
    for part in qualname.split("."):
        if part == "<locals>":
            raise TypeError(f"cannot resolve local object {qualname!r}")
        current = getattr(current, part)
    return current


def _load_user_function_global(module_name: str, qualname: str) -> Any:
    module = importlib.import_module(module_name)
    return _resolve_qualname_attr(module, qualname)


def _mangle_private_name_for_owner(name: str, private_owner: str | None) -> str:
    if not private_owner or not isinstance(name, str):
        return name
    if not name.startswith("__") or name.endswith("__") or "." in name:
        return name
    owner = private_owner.lstrip("_")
    if not owner:
        return name
    return f"_{owner}{name}"


def _contains_non_none_return(fn_node: ast.FunctionDef) -> bool:
    class ReturnVisitor(ast.NodeVisitor):
        def __init__(self):
            self.found = False

        def visit_Return(self, node: ast.Return) -> None:
            if node.value is None:
                return
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                return
            self.found = True

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

    visitor = ReturnVisitor()
    for stmt in fn_node.body:
        visitor.visit(stmt)
        if visitor.found:
            return True
    return False


def _lambda_to_function_def(lambda_node: ast.Lambda) -> ast.FunctionDef:
    func_kwargs: dict[str, Any] = {
        "name": "__pynterp_run_func_target__",
        "args": lambda_node.args,
        "body": [ast.Return(value=lambda_node.body)],
        "decorator_list": [],
        "returns": None,
        "type_comment": None,
    }
    if "type_params" in ast.FunctionDef._fields:
        func_kwargs["type_params"] = []
    function_node = ast.FunctionDef(**func_kwargs)
    return ast.copy_location(function_node, lambda_node)


def _build_user_function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    defaults: list[Any],
    kw_defaults: list[Any],
    annotations: Dict[str, Any],
) -> inspect.Signature:
    args = node.args
    parameters: list[inspect.Parameter] = []
    empty = inspect.Parameter.empty

    positional_args = list(getattr(args, "posonlyargs", []) or []) + list(getattr(args, "args", []) or [])
    default_start = max(0, len(positional_args) - len(defaults))

    for index, arg_node in enumerate(positional_args):
        if index < len(getattr(args, "posonlyargs", []) or []):
            kind = inspect.Parameter.POSITIONAL_ONLY
        else:
            kind = inspect.Parameter.POSITIONAL_OR_KEYWORD

        if index >= default_start:
            default = defaults[index - default_start]
        else:
            default = empty

        parameters.append(
            inspect.Parameter(
                arg_node.arg,
                kind,
                default=default,
                annotation=annotations.get(arg_node.arg, empty),
            )
        )

    if args.vararg is not None:
        parameters.append(
            inspect.Parameter(
                args.vararg.arg,
                inspect.Parameter.VAR_POSITIONAL,
                annotation=annotations.get(args.vararg.arg, empty),
            )
        )

    for index, arg_node in enumerate(args.kwonlyargs):
        default = kw_defaults[index] if index < len(kw_defaults) else NO_DEFAULT
        parameters.append(
            inspect.Parameter(
                arg_node.arg,
                inspect.Parameter.KEYWORD_ONLY,
                default=empty if default is NO_DEFAULT else default,
                annotation=annotations.get(arg_node.arg, empty),
            )
        )

    if args.kwarg is not None:
        parameters.append(
            inspect.Parameter(
                args.kwarg.arg,
                inspect.Parameter.VAR_KEYWORD,
                annotation=annotations.get(args.kwarg.arg, empty),
            )
        )

    return inspect.Signature(parameters, return_annotation=annotations.get("return", empty))


def _make_user_function_annotate(user_function: "UserFunction"):
    def __annotate__(format, /):
        return dict(user_function.__annotations__)

    return __annotate__


def adapt_user_function_for_interpreters_run_func(func: "UserFunction") -> Any:
    """Convert an interpreted function into a native function for _interpreters.run_func()."""
    node = func.node
    if isinstance(node, ast.Lambda):
        prepared_node = _lambda_to_function_def(copy.deepcopy(node))
    elif isinstance(node, ast.FunctionDef):
        prepared_node = copy.deepcopy(node)
    else:
        raise ValueError("_interpreters.run_func() requires a function defined with 'def'")
    if func.is_generator or func.is_async or func.is_async_generator:
        raise ValueError("_interpreters.run_func() does not support generators or async functions")
    if func.closure:
        raise ValueError("_interpreters.run_func() does not support closures")

    args = prepared_node.args
    has_args = bool(args.posonlyargs or args.args or args.vararg or args.kwonlyargs or args.kwarg)
    if has_args:
        raise ValueError("_interpreters.run_func() requires a function that takes no arguments")
    if _contains_non_none_return(prepared_node):
        raise ValueError("_interpreters.run_func() does not support non-None return values")

    prepared_node.name = "__pynterp_run_func_target__"
    prepared_node.decorator_list = []
    module = ast.Module(body=[prepared_node], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = dict(func.globals)
    namespace.setdefault("__builtins__", func.builtins)
    compiled = compile(module, func.code.filename, "exec")
    exec(compiled, namespace, namespace)
    return namespace[prepared_node.name]


class BoundMethod:
    def __init__(bound, func: "UserFunction", self_obj: Any):
        bound._func = func
        bound._self = self_obj
        bound.__name__ = getattr(func, "__name__", type(func).__name__)
        bound.__func__ = func

    def __call__(bound, *args, **kwargs):
        return bound._func(bound._self, *args, **kwargs)

    def __repr__(bound) -> str:
        return f"<bound method {bound._func!r} of {bound._self!r}>"

    def __getattr__(bound, name: str) -> Any:
        # Mirror native bound-method behavior: expose function metadata attrs
        # like unittest's __unittest_expecting_failure__ markers.
        return getattr(bound._func, name)


class UserFunction:
    """
    A callable representing a user-defined function interpreted by Interpreter.

    Implements descriptor protocol so it behaves like a Python function when placed
    on a class (so __init__ gets self bound, methods bind self, etc).
    """

    # Keep interpreter execution state out of __dict__ so functools.update_wrapper()
    # only copies user metadata (matching native function behavior).
    __slots__ = (
        "__dict__",
        "__weakref__",
        "node",
        "code",
        "globals",
        "builtins",
        "scope_info",
        "closure",
        "defaults",
        "kw_defaults",
        "__defaults__",
        "__kwdefaults__",
        "is_generator",
        "is_async",
        "is_async_generator",
        "__name__",
        "__qualname__",
        "__annotate__",
        "__annotations__",
        "__type_params__",
        "__signature__",
        "_private_owner",
    )

    def __init__(
        self,
        interpreter: "Interpreter",
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        scope_info: ScopeInfo,
        closure: Dict[str, Cell],
        defaults: list[Any],
        kw_defaults: list[Any],
        is_generator: bool,
        is_async: bool = False,
        is_async_generator: bool = False,
        qualname: str | None = None,
        type_params: tuple[Any, ...] = (),
        annotations: Dict[str, Any] | None = None,
        private_owner: str | None = None,
    ):
        self.node = node
        self.code = code
        self.globals = globals_dict
        self.builtins = builtins_dict
        self.scope_info = scope_info
        self.closure = dict(closure)
        self.defaults = list(defaults)
        self.kw_defaults = list(kw_defaults)
        self.__defaults__ = tuple(self.defaults) if self.defaults else None
        kwonlyargs = list(getattr(node.args, "kwonlyargs", []) or [])
        kwdefault_map: dict[str, Any] = {}
        for arg_node, default_value in zip(kwonlyargs, self.kw_defaults):
            if default_value is NO_DEFAULT:
                continue
            name = _mangle_private_name_for_owner(arg_node.arg, private_owner)
            kwdefault_map[name] = default_value
        self.__kwdefaults__ = kwdefault_map or None
        self.is_generator = is_generator
        self.is_async = is_async
        self.is_async_generator = is_async_generator
        if self.is_async and not self.is_async_generator:
            if hasattr(inspect, "markcoroutinefunction"):
                inspect.markcoroutinefunction(self)
        name = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<lambda>"
        self.__name__ = name
        self.__qualname__ = qualname if qualname is not None else name
        self.__module__ = globals_dict.get("__name__", "__main__")
        self.__annotations__ = dict(annotations) if annotations is not None else {}
        self.__annotate__ = _make_user_function_annotate(self)
        self.__type_params__ = tuple(type_params)
        self.__signature__ = _build_user_function_signature(
            node,
            self.defaults,
            self.kw_defaults,
            self.__annotations__,
        )
        self._private_owner = private_owner
        _USER_FUNCTION_INTERPRETERS[self] = interpreter

    def __repr__(self) -> str:
        if self.is_async_generator:
            kind = "async-gen"
        elif self.is_async:
            kind = "async"
        elif self.is_generator:
            kind = "gen"
        else:
            kind = "func"
        return f"<UserFunction {self.__name__} ({kind})>"

    def __call__(user_function, *args, **kwargs):
        try:
            interpreter = _USER_FUNCTION_INTERPRETERS[user_function]
        except KeyError as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError("interpreted function is detached from interpreter") from exc
        return interpreter._call_user_function(user_function, args, kwargs)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return BoundMethod(self, obj)

    def __reduce_ex__(self, protocol: int):
        return self.__reduce__()

    def __reduce__(self):
        module_name = self.__module__
        if not isinstance(module_name, str):
            raise TypeError(f"cannot pickle {type(self).__name__!r} object without module")

        qualname = self.__qualname__
        if not isinstance(qualname, str):
            raise TypeError(f"cannot pickle {type(self).__name__!r} object with invalid qualname")
        if "<locals>" in qualname:
            raise TypeError(f"cannot pickle local interpreted function {qualname!r}")

        resolved = _load_user_function_global(module_name, qualname)
        if resolved is not self:
            raise TypeError(
                f"cannot pickle interpreted function {module_name}.{qualname}: "
                "it is not the current module global"
            )
        return (_load_user_function_global, (module_name, qualname))
