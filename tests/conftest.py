from __future__ import annotations

import sys
from pathlib import Path

# Allow importing the package when running plain `pytest` without an editable install.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

import pytest

from pynterp import Interpreter


@pytest.fixture
def run_interpreter():
    def _run(source: str, *, allowed_imports=None, env=None, filename: str = "<test>"):
        interpreter = Interpreter(allowed_imports=allowed_imports)
        globals_dict = {} if env is None else dict(env)
        interpreter.run(source, env=globals_dict, filename=filename)
        return globals_dict

    return _run
