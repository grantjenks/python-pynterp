# pynterp

`pynterp` is an AST-walk interpreter for a substantial, tested subset of Python.

## Project focus

- readable interpreter internals (AST + explicit runtime scopes)
- deterministic execution through explicit environments
- measured behavior against CPython tests

## Compatibility

- host runtime: CPython `3.10+` (`requires-python >=3.10`)
- language support tracks modern CPython AST features, including:
  - structural pattern matching (`match` / `case`)
  - exception groups (`except*`)
  - generic type parameter syntax and runtime typing objects
  - template strings (`TemplateStr`) when running on Python `3.14+`

## Quickstart

```pycon
>>> from pynterp import Interpreter
>>> interpreter = Interpreter()
>>> env = interpreter.make_default_env()
>>> run_result = interpreter.run("""
... print("Hello, World!")
... """, env=env)
Hello, World!
```

## What is implemented

### Core execution model

- explicit env execution: `Interpreter.run(source, env=...)` requires a dict
- no implicit inheritance of host globals/builtins
- `RunResult` return model captures uncaught exceptions without forcing immediate raise
- interpreter-aware handling for `globals()`, `locals()`, `vars()`, `dir()`, `eval()`, and `exec()`

### Statement support

- assignment forms: `=`, annotated assignment, augmented assignment, destructuring/starred targets
- control flow: `if`, `while`, `for`, `break`, `continue`, loop `else`
- function forms: `def`, `async def`, `return`, `global`, `nonlocal`
- class definitions with metaclass namespace handling (`__prepare__`) and private-name mangling
- exception handling: `try/except/else/finally`, `raise`, `raise ... from ...`, `try/except*`
- context managers: `with`, `async with`
- pattern matching: value/singleton/sequence/mapping/class/or/as patterns with guards
- imports: `import`, `from ... import ...`, optional relative import support
- type alias statement (`type X = ...`) with type parameter support

### Expression support

- scalar and operator forms: constants, names, unary/binary/bool ops, chained comparisons, conditional expressions, walrus
- calls with CPython-like argument binding checks (`*args`, `**kwargs`, duplicate-key errors)
- containers and indexing: list/tuple/set/dict literals, starred unpacking, attributes, subscripts, slices
- string forms: f-strings and template strings (runtime-dependent for 3.14 features)
- functional forms: lambdas, comprehensions, generator expressions, `yield`, `yield from`, `await`

### Functions, scopes, and runtime semantics

- lexical scoping with closure cells and `nonlocal` behavior
- descriptor-correct method binding (`UserFunction` + `BoundMethod`)
- zero-argument `super()` support via `__class__` closure behavior
- function metadata and interoperability: defaults/kwdefaults mutation, annotations, signatures, weakrefs, pickling paths
- class/generic metadata wiring including `__qualname__`, `__orig_bases__`, and `__type_params__` where applicable

### Async and generator runtime

- generator execution path mirrors statement/expression semantics in generator mode
- async function execution with awaitable protocol handling
- interpreted async generator object with `asend`, `athrow`, and `aclose` behavior

### Environment controls and hardening

- allowlist-based import control (`allowed_imports`)
- safe builtins surface (for example no implicit `open`)
- guarded reflection pivots via wrapped `getattr`/`setattr`/`delattr`/`hasattr`
- blocked high-risk attributes include names such as `__mro__`, `__subclasses__`, `__globals__`, frame globals/locals, and related pivots

This is in-process hardening, not an OS sandbox.
Out of scope: CPU/memory/time quotas and process/kernel isolation.

### Interpreted module loading

- optional interpreted package imports via `InterpretedModuleLoader`
- interpreted modules can import each other through the interpreter runtime
- the project can interpret code that imports and runs `pynterp` itself (see bootstrap tests)

### Tests in this repo

- `~711` tests across CLI behavior, semantics, security hardening, keyword binding, `super()` semantics, bootstrap/self-interpretation checks, and probe correctness
- large dedicated security suite exercises reflective escape attempts and descriptor rebound edge cases

## CPython compatibility probe

Probe script: [`scripts/cpython_pynterp_probe.py`](scripts/cpython_pynterp_probe.py)

Reproducible module-mode probe command (from script header):

```bash
uv run python scripts/cpython_pynterp_probe.py \
  --cpython-root /tmp/cpython-3.14 \
  --python-exe /tmp/cpython-3.14/python.exe \
  --basis tests \
  --mode module \
  --strict-worker-match \
  --json-out /tmp/pynterp-probe-tests-module.json
```

Default unsupported source filters used by the probe classifier:

- `__import__`
- `__dict__`
- `__code__`

Snapshot baseline (February 27, 2026; CPython `origin/3.14`, `module` mode, `basis=tests`):

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
- individual pass+skip rate: `69.40%`

`script` mode (`__name__ == "__main__"`) is much lower and mainly useful for diagnosing entry-point assumptions (same run, `--mode script`):

- individual pass rate: `4.11%`
- individual pass+skip rate: `7.92%`
