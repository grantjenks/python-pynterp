from __future__ import annotations

import sys
from pathlib import Path

from .main import Interpreter


def _usage() -> str:
    return "usage: python -m pynterp <script.py>"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_usage(), file=sys.stderr)
        return 2

    script_path = Path(args[0]).resolve()
    if not script_path.is_file():
        print(f"pynterp: script not found: {script_path}", file=sys.stderr)
        return 2

    source = script_path.read_text()
    interpreter = Interpreter()
    env = interpreter.make_default_env(
        env={
            "__file__": str(script_path),
            "__package__": None,
        },
        name="__main__",
    )
    interpreter.run(source, env=env, filename=str(script_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
