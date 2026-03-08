---
name: capture-the-flag
description: Develop and validate a sandbox escape that works against the live `pynterp.gmj.dev` challenge or the local challenge implementation. Use when asked to inspect pynterp hardening, build exploit probes, reproduce the service locally, iterate toward a working `/run` payload, or capture the flag from `/challenge/flag.txt`.
---

# Capture The Flag

Target the live service contract, the current hardening, and the local codebase together. Optimize for a payload that actually works against `https://pynterp.gmj.dev/run`, not a generic Python sandbox idea.

## Start from the deployed contract

Read these files first:

- `README.md`: public challenge framing and endpoint examples
- `www/app.py`: exact `/run` contract; POST `{"code": "..."}`
- `www/Dockerfile`: runtime is `python:3.14-slim`, the package comes from PyPI, and the flag lives at `/challenge/flag.txt`

The `/run` response contains `ok`, `stdout`, `stderr`, `error`, and `exception_type`. Treat `stdout` as the primary success channel.

## Read current hardening before proposing probes

Inspect these hotspots:

- `src/pynterp/lib/guards.py`
- `src/pynterp/lib/builtins.py`
- `src/pynterp/expressions.py`
- `src/pynterp/statements.py`
- `src/pynterp/functions.py`
- `src/pynterp/host_exec.py`
- `tests/test_sandbox_security.py`
- `tests/test_sandbox_typealias_escape.py`

Start with a focused search:

```bash
rg -n "escape|probe|__builtins__|__globals__|__call__|signature|typealias|eval|exec" tests src/pynterp
```

Use the tests to avoid spending time on already-closed pivots.

## Prefer local reproduction first

Use the same interpreter configuration as the live service:

```python
from pynterp import Interpreter

interp = Interpreter(allowed_imports=set())
env = interp.make_default_env(name="__main__")
result = interp.run(source, env=env, filename="<user>")
```

Use direct `Interpreter` probes for fast iteration. Use `uv run flask --app www.app run` or `uv run poe www` only when the HTTP layer matters. If behavior looks version-sensitive, reproduce it under Python 3.14 or through the `www` Docker image.

Keep temporary scripts out of the repo, or delete them before finishing.

## Use the right search strategy

Deprioritize pivots that the tests already cover heavily:

- direct `__globals__`, `__builtins__`, frame, traceback, `__mro__`, or `__subclasses__` access
- direct `__call__` access on wrapped safe builtins
- deleting `__builtins__` and hoping host `eval`, `exec`, or `type Alias` restores unsafe builtins

Look for mismatches between interpreted execution and host execution instead:

- helper paths that still call host `eval` or `exec`
- typing and annotation evaluation paths
- descriptor rebinding and alternate attribute-resolution paths
- mutable metadata on wrapper objects
- globals or locals reconstruction bugs
- module loader state, exception objects, generators, coroutines, or other reflective surfaces that are not fully guarded

## Develop payloads incrementally

Follow this loop:

1. Form a narrow hypothesis from code.
2. Write the smallest local probe that proves or disproves it.
3. Surface the result with `print(...)` or a sentinel file read.
4. Promote only a locally successful primitive to the live `/run` endpoint.
5. Turn the primitive into a final payload that prints `/challenge/flag.txt`.

Keep probes small. Prefer one primitive per probe. Avoid huge monolithic payloads until the primitive is already proven.

## Validate against the live service

Use Python or `curl` so multiline payloads are easy to quote:

```bash
python3 - <<'PY'
import json, urllib.request

code = """print(1 + 2)"""
req = urllib.request.Request(
    "https://pynterp.gmj.dev/run",
    data=json.dumps({"code": code}).encode(),
    headers={"content-type": "application/json"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    print(resp.status)
    print(resp.read().decode())
PY
```

The winning payload should print the flag, not just stash it in a variable.

## Turn discoveries into repo knowledge

When the task includes patching the escape afterward, tie the exploit back to a concrete file and add a regression test. Put narrow follow-up probes near existing coverage in `tests/test_sandbox_security.py`, or create a new focused test file when the theme is distinct.

## Remember the current hardening

Treat these paths as recently hardened:

- safe builtins are wrapped in immutable callable objects in `src/pynterp/lib/builtins.py`
- `__call__` is blocked in `src/pynterp/lib/guards.py`
- `src/pynterp/host_exec.py` prevents host `eval` and `exec` from reinjecting unsafe builtins
- `tests/test_sandbox_typealias_escape.py` covers `type Alias`, builtin `eval`, and builtin `exec` after `__builtins__` deletion

Search for a path the tests do not already name.
