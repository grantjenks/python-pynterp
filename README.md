# pynterp

`pynterp` is an AST-walk interpreter for a meaningful subset of Python.

## Why this project exists

The project is focused on:

- a readable interpreter core (AST + explicit runtime scopes),
- deterministic, explicit execution environments,
- self-hosting/bootstrap experiments (interpreter interpreting itself),
- measurable compatibility against CPython tests.

## Key requirements and design decisions

1. Explicit runtime environment only.
- `Interpreter.run(source, env=...)` requires an explicit dict.
- No automatic inheritance of host globals or builtins.

2. Single runtime policy.
- There is no separate permissive bootstrap mode.
- Use `make_default_env(...)` for both regular execution and bootstrap/self-hosting scenarios.

3. In-process hardening for untrusted code (best effort, not OS isolation).
- Guarded attribute access blocks reflection pivots used for escapes (`__mro__`, `__subclasses__`, frame globals, etc.).
- Builtins are explicit and wrapped where needed (`getattr`/`setattr`/`delattr`/`hasattr` policy checks).

4. Interpreted module loading.
- `pynterp` modules can be loaded through interpreter execution (`InterpretedModuleLoader`) for bootstrap/self-hosting paths.

5. Non-cheating bootstrap test.
- Bootstrap test imports `pynterp.main.Interpreter` through interpreted import machinery and executes the kitchen-sink fixture.

6. Tooling and layout.
- `pyproject.toml` + `uv`
- `ruff` for lint/format checks
- `pytest`
- source under `src/pynterp/`, tests under `tests/`

7. CLI execution.
- `uv run python -m pynterp tests/fixtures/kitchen_sink.py` runs interpreted scripts.

## Security scope

In-process hardening is implemented, but this is not an OS-level sandbox boundary.

- Included: strict env control, import controls, reflection guardrails.
- Out of scope: CPU/memory/time isolation and kernel/process isolation.

## CPython 3.14 compatibility probe

Probe script:
- [`scripts/cpython_pynterp_probe.py`](/Users/grantjenks/repos/python-pynterp/scripts/cpython_pynterp_probe.py)

Default unsupported filters in probe:
- `__import__`
- `__dict__`
- `__code__`

Baseline run (CPython `origin/3.14`, built interpreter at `/tmp/cpython-3.14/python.exe`):

- basis: `tests` (individual unittest cases, with blocked-file accounting)
- mode: `module`
- total test files: `762`
- applicable files: `515` (`67.59%`)
- not applicable files: `247`
- declared individual tests in applicable files: `10,761`
- discovered+run individual tests: `12,560`
- estimated individual tests total: `15,339`
- individual pass: `9,406`
- individual skip: `1,239`
- individual fail: `4,694`
- pass rate (individual): `61.32%`
- pass+skip rate (individual): `69.40%`

`script` mode (`__name__ == "__main__"`) is much lower and mainly useful for diagnosing entry-point assumptions:
- pass rate (individual): `4.11%`
- pass+skip rate (individual): `7.92%`

## Running the probe

Module mode, individual-test basis:

```bash
uv run python /Users/grantjenks/repos/python-pynterp/scripts/cpython_pynterp_probe.py \
  --cpython-root /tmp/cpython-3.14 \
  --python-exe /tmp/cpython-3.14/python.exe \
  --basis tests \
  --mode module \
  --json-out /tmp/pynterp-probe-tests-module.json
```

Script mode, individual-test basis:

```bash
uv run python /Users/grantjenks/repos/python-pynterp/scripts/cpython_pynterp_probe.py \
  --cpython-root /tmp/cpython-3.14 \
  --python-exe /tmp/cpython-3.14/python.exe \
  --basis tests \
  --mode script \
  --json-out /tmp/pynterp-probe-tests-script.json
```

To override unsupported filters:

```bash
uv run python /Users/grantjenks/repos/python-pynterp/scripts/cpython_pynterp_probe.py \
  --cpython-root /tmp/cpython-3.14 \
  --python-exe /tmp/cpython-3.14/python.exe \
  --basis tests \
  --mode module \
  --no-default-unsupported \
  --unsupported-pattern '\\b_tkinter\\b'
```
