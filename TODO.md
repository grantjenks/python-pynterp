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
- Metrics: `tests/test_sandbox_security.py` cases 6 -> 8 (+2). Validation gates this iteration: `8 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).

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
