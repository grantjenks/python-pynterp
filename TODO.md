# TODO

## Primary Goal

Build `pynterp` into a secure in-process sandbox for untrusted code, assuming the host provides an explicit, trusted `env`.

## Scope

### In scope

- Prevent sandbox escape to host globals, host builtins, importers, files, process APIs, and interpreter internals.
- Keep sandbox policy explicit and testable.
- Preserve deterministic behavior for allowed language/runtime subset.

### Out of scope

- CPU/memory/wall-clock isolation.
- OS/container/kernel isolation.
- Side-channel hardening.

## Threat Model

- Attacker controls interpreted source text.
- Attacker can chain Python introspection/metaprogramming tricks.
- Host controls interpreter configuration (`env`, allowed imports, safe stdlib surface).
- A security bug means attacker can reach host capabilities outside that explicit surface.

## Security Invariants (Must Hold)

1. `Interpreter.run()` never auto-inherits host globals/builtins.
2. Builtins exposed to guest code are explicit allowlist-only.
3. Import resolution is allowlist-only and cannot bypass via reflective pivots.
4. Guarded attributes block known escape pivots (`__subclasses__`, frame globals/builtins/locals, etc.).
5. Exception/traceback/generator/coroutine objects cannot be used to recover host capabilities.
6. No path from guest objects to host module loader, `sys.modules`, or unrestricted import mechanisms.

## Priority Backlog

1. Expand escape test corpus (highest priority).
- Add adversarial tests for: traceback/frame pivot chains, descriptor abuse, `super()`/MRO tricks, pickling/reduction hooks, closure/cell leaks, metaclass abuse, async/generator frame tricks, and import smuggling.
- Done when: `tests/test_sandbox_security.py` has broad attack coverage and every new blocked path has a regression test.
- Progress (2026-02-27, iteration 1): added regression tests for interpreter-policy pivot attempts (`probe.interpreter...` and `object.__getattribute__(probe, "interpreter")`) and removed direct `UserFunction -> Interpreter` attribute exposure.
- Progress (2026-02-27, iteration 2): added regression tests for closure/cell leak pivots (`fn.__closure__[0].cell_contents`), direct `__reduce_ex__` reduction-hook access, and `object.__getattribute__` reduction-hook bypass attempts.
- Progress (2026-02-27, iteration 3): added descriptor/super/metaclass adversarial regressions for blocked-attribute bypass attempts via `type.__getattribute__`, `super(...).__getattribute__`, and custom metaclass `__getattribute__` dispatch.
- Progress (2026-02-28, iteration 4): added import-smuggling regressions for `math.__loader__` and `math.__spec__.loader` chains, plus an `object.__getattribute__` bypass attempt; tightened blocked attrs to deny `__loader__`/`__spec__` metadata pivots.
- Progress (2026-02-28, iteration 5): added traceback/frame and coroutine-frame adversarial regressions for `tb.tb_next -> tb_frame -> f_locals`, `object.__getattribute__(tb.tb_frame, "f_globals")`, and `co.cr_frame.f_locals` pivot attempts.
- Progress (2026-02-28, iteration 6): added exception-chain traceback regressions for `exc.__context__.__traceback__` and `exc.__cause__.__traceback__` frame pivots, plus an `object.__getattribute__` bypass attempt reaching context traceback/frame globals.
- Progress (2026-02-28, iteration 7): added object-getattribute regressions for coroutine/async-generator frame pivots (`co.cr_frame -> f_globals`, `ag.ag_frame -> f_locals`) and traceback-chain navigation (`tb_next -> tb_frame -> f_locals`).
- Progress (2026-02-28, iteration 8): added pickling-reduction regressions for `__reduce__` and `object.__getattribute__(..., "__reduce__")`, plus a generator-frame bypass regression using `object.__getattribute__(gen, "gi_frame")`.
- Progress (2026-02-28, iteration 9): added builtin-callable `__self__` pivot regressions to prevent recovering the host `builtins` module via direct attribute access, `object.__getattribute__`, or `type.__getattribute__`.
- Progress (2026-02-28, iteration 10): added traceback/coroutine frame `f_builtins` regressions for direct traceback access plus `object.__getattribute__` bypass attempts on traceback and coroutine frames.
- Progress (2026-02-28, iteration 11): added importer `__self__` pivot regressions to prevent recovering interpreter/loader objects via `__import__.__self__` through direct access, `object.__getattribute__`, and `type.__getattribute__`.
- Metrics: `tests/test_sandbox_security.py` cases 6 -> 8 (+2). Validation gates this iteration: `8 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 8 -> 11 (+3). Validation gates this iteration: `11 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 11 -> 14 (+3). Validation gates this iteration: `14 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 14 -> 17 (+3). Validation gates this iteration: `17 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 17 -> 20 (+3). Validation gates this iteration: `20 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 20 -> 23 (+3). Validation gates this iteration: `23 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 23 -> 26 (+3). Validation gates this iteration: `26 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 26 -> 29 (+3). Validation gates this iteration: `29 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 29 -> 32 (+3). Validation gates this iteration: `32 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 32 -> 35 (+3). Validation gates this iteration: `35 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 35 -> 38 (+3). Validation gates this iteration: `38 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).

2. Lock down object graph pivots.
- Review and tighten blocked attrs and special-case aliases in `src/pynterp/lib/guards.py`.
- Verify no alternate access path bypasses policy (bound/unbound descriptors, `object.__getattribute__`, wrapper objects).
- Done when: targeted red-team tests for known pivots all fail safely with policy errors.

3. Strict import boundary verification.
- Ensure no route to host imports outside `import_safe_stdlib_module()` and configured allowlist.
- Add tests for bypass attempts via `__import__` indirection, module metadata abuse, and loader/spec manipulation.
- Done when: bypass attempts are blocked and validated in tests.

4. Builtins minimization pass.
- Re-evaluate every builtin in `src/pynterp/lib/builtins.py` for sandbox necessity.
- Remove or wrap risky entries where possible, and document rationale per exposed builtin.
- Done when: builtins allowlist has explicit per-item justification and security tests remain green.

5. Define security policy profile.
- Write a concise policy doc for what is intentionally allowed vs blocked.
- Include compatibility tradeoffs and non-goals.
- Done when: policy is versioned and test expectations map directly to it.

## Validation Gates

Run on every sandbox-focused change:

```bash
uv run pytest tests/test_sandbox_security.py -q
uv run pytest tests/test_env_strict.py -q
uv run pytest tests/test_core_semantics.py -k "attr_guard or traceback or frame or import" -q
```

## Notes

- Compatibility and performance work are important but secondary until the sandbox boundary is stronger and better tested.
- If a compatibility fix weakens sandbox guarantees, reject it unless policy is intentionally changed and documented.
- For tradeoffs made regarding compatibility and utility, document those in TRADEOFFS.md for later review.
