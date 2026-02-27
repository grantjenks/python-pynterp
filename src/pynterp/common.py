from __future__ import annotations

from typing import Any

UNBOUND = object()
NO_DEFAULT = object()


class ControlFlowSignal(BaseException):
    """Internal non-user exceptions used for control flow (return/break/continue)."""


class ReturnSignal(ControlFlowSignal):
    def __init__(self, value: Any):
        self.value = value


class BreakSignal(ControlFlowSignal):
    pass


class ContinueSignal(ControlFlowSignal):
    pass


class Cell:
    """A tiny closure cell."""

    __slots__ = ("value",)

    def __init__(self, value: Any = UNBOUND):
        self.value = value

    def __repr__(self) -> str:
        return "<Cell UNBOUND>" if self.value is UNBOUND else f"<Cell {self.value!r}>"
