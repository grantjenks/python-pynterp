# TODO

## Status

- Date: 2026-02-27
- Full local test suite: `83 passed, 3 skipped`
- Probe baseline source: CPython `origin/3.14` (`a58ea8c2123`)
- Probe command: `scripts/cpython_pynterp_probe.py --basis tests --mode module`
- Default unsupported filters: `__import__`, `__dict__`
- Latest full probe artifact: `/tmp/pynterp-probe-tests-module-20260227-iter001.json`

## Compatibility Snapshot

### Baseline (initial)

- applicable files: `515 / 762` (`67.59%`)
- estimated individual tests: `15,339`
- pass: `9,406`
- skip: `1,239`
- fail: `4,694`
- pass rate: `61.32%`
- pass+skip rate: `69.40%`

### Latest full probe result recorded

From full module/tests probe run on `2026-02-27` (`/tmp/pynterp-probe-tests-module-20260227-iter001.json`):

- applicable files: `515 / 762` (`67.59%`)
- estimated individual tests: `15,686`
- pass: `12,665` (`+924` vs `iter-009`)
- skip: `1,305` (`-2` vs `iter-009`)
- fail: `1,716` (`-955` vs `iter-009`)
- pass+skip rate: `89.06%` (`+6.05pp` vs `iter-009`)
- top fail categories: `TIMEOUT (751)`, `ModuleNotFound/'_tkinter' (470)`, `Suite/Error (238)`, `Suite/Failure (173)`
- top suite-error signatures: `when serializing pynterp.functions.UserFunction object (25)`, `__code__ blocked (22)`, `messages.po missing (15)`, `importlib.metadata missing (12)`, `_interpreters.run_func() arg 2 type mismatch (9)`

## Explicit Skip Policy

Use this section as the source of truth for intentional exclusions.

### Default probe skips (regex)

- `\b__import__\b`
- `\b__dict__\b`

### Explicitly out of scope (current)

- Optional GUI stack (`_tkinter`, `Lib/test/test_tkinter/*`) unless dependency/runtime support is explicitly enabled.
- CPython implementation-detail and C-API-heavy test families:
- `Lib/test/test_capi/*`
- `_testcapi`, `_testinternalcapi`, `_testlimitedcapi`, `_testclinic`
- `cpython_only`, `check_impl_detail`, `gettotalrefcount` markers
- OS/process sandboxing concerns (CPU, memory, wall-time isolation) are out of scope for this in-process interpreter compatibility metric.

### Sandbox compatibility boundary

- Reflection pivots remain blocked by policy and are not compatibility targets by default:
- `__code__`-adjacent introspection
- frame/global pivots such as `f_globals` and `f_builtins`
- Any change here must be treated as a deliberate policy change and updated in this file before comparing metrics.

### Probe comparison rule

- Every reported KPI must include the exact unsupported patterns used.
- Do not compare runs with different skip filters as a single trendline.

## Priority Backlog

1. [done] Re-run full CPython module-basis probe and refresh canonical metrics.
- Done when: `TODO.md` snapshot is updated from a new full run (not targeted reruns), with top fail categories and top suite error signatures.
- Progress (2026-02-27): Captured `/tmp/pynterp-probe-tests-module-20260227-iter001.json` and refreshed snapshot metrics/categories/signatures above.

2. Reduce remaining `Suite/Error` bucket first.
- Done when: top 10 current suite-error signatures each show clear net reduction in a full probe rerun.
- Progress (2026-02-27, iter 002): Added pickle reduction support for module-level `pynterp.functions.UserFunction` via `__module__` + `__reduce__/__reduce_ex__` global resolution.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "pickle"` => `2 passed` (new user-function pickle roundtrip regression included); `uv run pytest tests/test_core_semantics.py` => `64 passed, 3 skipped`.
- Expected full-probe delta on next rerun: suite-error signature `when serializing pynterp.functions.UserFunction object` should drop from `25` toward `0` (pending measurement).
- Progress (2026-02-27, iter 003): Added safe-stdlib support for `importlib.metadata` with a constrained `importlib` proxy that only exposes `metadata`, plus regression coverage for dotted import and alias import paths.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "importlib_metadata or import_dotted_module"` => `3 passed`; `uv run pytest tests/test_core_semantics.py` => `65 passed, 3 skipped`.
- Expected full-probe delta on next rerun: suite-error signature `ModuleNotFoundError: No module named 'importlib.metadata'` should drop from `12` toward `0` (pending measurement).
- Progress (2026-02-27, iter 004): Added runtime `_interpreters.run_func` compatibility adapter that retries `UserFunction` arguments as synthesized native `def` functions (with explicit `ValueError` validation for unsupported args/closures/non-`None` returns), and applied module patching on both import and runtime-call return paths.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "interpreters_run_func"` => `2 passed`; `uv run pytest tests/test_core_semantics.py` => `67 passed, 3 skipped`; targeted CPython 3.14 diagnostic (`RunFuncTests`) => `5 passed, 1 error` (remaining error is policy-blocked `__code__` access, not `run_func` arg-type mismatch).
- Expected full-probe delta on next rerun: suite-error signature `TypeError: _interpreters.run_func() argument 2 must be a function, not UserFunction` should drop from `9` toward `0` (pending measurement).

3. Reduce timeout-heavy modules.
- Target files: `test_asyncio/test_events.py`, `test_queue.py`, `test_sched.py`, `test_thread.py`, `test_zipfile64.py`.
- Done when: timeout category count decreases measurably in full probe output.

4. Reduce `Suite/Failure` assertion mismatches.
- Start with top files from the next full probe report.
- Done when: full-probe `Suite/Failure` category count decreases.

5. Decide and document long-term sandbox compatibility policy for blocked attrs.
- Current explicit skips include `__import__` and `__dict__` in probe filters.
- Done when: policy is explicit for `__code__`-adjacent introspection and reflected in probe filters/tests.

## Guardrails

- Keep unsupported filters explicit and versioned in probe invocations.
- Do not mix environment-missing dependency failures with interpreter semantic failures when reporting progress.
- Use full-probe numbers as the primary KPI; treat targeted reruns as local diagnostics only.
