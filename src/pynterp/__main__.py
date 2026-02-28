import argparse
import sys
import traceback
from pathlib import Path

from .main import Interpreter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pynterp",
        usage="python -m pynterp <script.py>",
    )
    parser.add_argument("script")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args_list = sys.argv[1:] if argv is None else argv
    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        return int(exc.code)

    script_path = Path(args.script).resolve()
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
    result = interpreter.run(source, env=env, filename=str(script_path))
    if result.exception is not None:
        exc = result.exception
        if isinstance(exc, SystemExit):
            code = exc.code
            if code is None:
                return 0
            if isinstance(code, int):
                return code
            print(code, file=sys.stderr)
            return 1
        traceback.print_exception(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
