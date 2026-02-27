from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any, Dict

from .code import ModuleCode, ScopeInfo
from .common import Cell

if TYPE_CHECKING:
    from .main import Interpreter


class BoundMethod:
    def __init__(self, func: "UserFunction", self_obj: Any):
        self._func = func
        self._self = self_obj
        self.__name__ = getattr(func, "__name__", type(func).__name__)

    def __call__(self, *args, **kwargs):
        return self._func(self._self, *args, **kwargs)

    def __repr__(self) -> str:
        return f"<bound method {self._func!r} of {self._self!r}>"


class UserFunction:
    """
    A callable representing a user-defined function interpreted by Interpreter.

    Implements descriptor protocol so it behaves like a Python function when placed
    on a class (so __init__ gets self bound, methods bind self, etc).
    """

    def __init__(
        self,
        interpreter: "Interpreter",
        node: ast.FunctionDef,
        code: ModuleCode,
        globals_dict: dict,
        builtins_dict: dict,
        scope_info: ScopeInfo,
        closure: Dict[str, Cell],
        defaults: list[Any],
        kw_defaults: list[Any],
        is_generator: bool,
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
        self.__name__ = node.name
        self.__qualname__ = node.name

    def __repr__(self) -> str:
        kind = "gen" if self.is_generator else "func"
        return f"<UserFunction {self.__name__} ({kind})>"

    def __call__(self, *args, **kwargs):
        return self.interpreter._call_user_function(self, args, kwargs)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return BoundMethod(self, obj)
