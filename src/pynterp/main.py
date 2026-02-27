from __future__ import annotations

from .core import InterpreterCore
from .expressions import ExpressionMixin
from .helpers import HelperMixin
from .statements import StatementMixin


class Interpreter(StatementMixin, ExpressionMixin, HelperMixin, InterpreterCore):
    pass
