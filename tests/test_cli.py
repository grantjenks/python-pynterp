from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_executes_kitchen_sink_script() -> None:
    script = Path(__file__).parent / "fixtures" / "kitchen_sink.py"
    proc = subprocess.run(
        [sys.executable, "-m", "pynterp", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


def test_module_requires_script_argument() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pynterp"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "usage: python -m pynterp <script.py>" in proc.stderr
