from __future__ import annotations

from pathlib import Path

from pynterp import Interpreter


def test_zero_arg_super_and___class___closure():
    interpreter = Interpreter(allow_relative_imports=True)
    env = interpreter.make_default_env(
        package_root=Path(__file__).resolve().parents[1] / "src" / "pynterp"
    )

    source = """
class Base:
    def __init__(self, start):
        self.value = start

class Child(Base):
    def __init__(self, start):
        super().__init__(start + 1)

    def klass(self):
        return __class__.__name__

c = Child(4)
RESULT = (c.value, c.klass())
"""

    interpreter.run(source, env=env, filename="<super_semantics>")
    assert env["RESULT"] == (5, "Child")
