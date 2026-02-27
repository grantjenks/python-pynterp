from __future__ import annotations

import ast
import copy
import importlib
from typing import TYPE_CHECKING, Any, Dict

from .code import ModuleCode, ScopeInfo
from .common import Cell

if TYPE_CHECKING:
    from .main import Interpreter


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


def adapt_user_function_for_interpreters_run_func(func: "UserFunction") -> Any:
    """Convert an interpreted function into a native function for _interpreters.run_func()."""
    node = func.node
    if not isinstance(node, ast.FunctionDef):
        raise ValueError("_interpreters.run_func() requires a function defined with 'def'")
    if func.is_generator or func.is_async or func.is_async_generator:
        raise ValueError("_interpreters.run_func() does not support generators or async functions")
    if func.closure:
        raise ValueError("_interpreters.run_func() does not support closures")

    args = node.args
    has_args = bool(args.posonlyargs or args.args or args.vararg or args.kwonlyargs or args.kwarg)
    if has_args:
        raise ValueError("_interpreters.run_func() requires a function that takes no arguments")
    if _contains_non_none_return(node):
        raise ValueError("_interpreters.run_func() does not support non-None return values")

    cloned = copy.deepcopy(node)
    cloned.name = "__pynterp_run_func_target__"
    cloned.decorator_list = []
    module = ast.Module(body=[cloned], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = dict(func.globals)
    namespace.setdefault("__builtins__", func.builtins)
    compiled = compile(module, func.code.filename, "exec")
    exec(compiled, namespace, namespace)
    return namespace[cloned.name]


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


class UserFunction:
    """
    A callable representing a user-defined function interpreted by Interpreter.

    Implements descriptor protocol so it behaves like a Python function when placed
    on a class (so __init__ gets self bound, methods bind self, etc).
    """

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
        self.interpreter = interpreter
        self.node = node
        self.code = code
        self.globals = globals_dict
        self.builtins = builtins_dict
        self.scope_info = scope_info
        self.closure = dict(closure)
        self.defaults = list(defaults)
        self.kw_defaults = list(kw_defaults)
        self.is_generator = is_generator
        self.is_async = is_async
        self.is_async_generator = is_async_generator
        name = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<lambda>"
        self.__name__ = name
        self.__qualname__ = qualname if qualname is not None else name
        self.__module__ = globals_dict.get("__name__", "__main__")
        self.__annotations__ = dict(annotations) if annotations is not None else {}
        self.__type_params__ = tuple(type_params)
        self._private_owner = private_owner

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
        return user_function.interpreter._call_user_function(user_function, args, kwargs)

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
