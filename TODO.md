# TODO

## Baseline (CPython 3.14, probe basis=`tests`, mode=`module`)

- Source snapshot: `origin/3.14` (`a58ea8c2123`)
- Probe command: `scripts/cpython_pynterp_probe.py --basis tests --mode module`
- Unsupported filters enabled: `__import__`, `__dict__`
- Applicable test files: `515 / 762` (`67.59%`)
- Estimated individual tests total: `15,339`
- Individual pass: `9,406`
- Individual skip: `1,239`
- Individual fail: `4,694`
- Individual pass rate: `61.32%`
- Individual pass+skip rate: `69.40%`

## Prioritized backlog (sorted by individual test impact)

1. Reduce `Suite/Error` failures (`2,490` tests impacted).
- Reason: this is the largest bucket and masks many correctness gaps.
- Requirement: extend the probe to emit top exception signatures from `unittest` `result.errors`, then implement fixes for the top 3 signatures first.

2. Implement `AsyncFunctionDef` support (`753` tests impacted).
- Reason: largest single missing AST statement form.
- Requirement: support async function definition/runtime behavior required by `asyncio` test modules.

3. SKIP ~~Define policy for optional GUI dependencies (`_tkinter`) (`470` tests impacted).~~
- Reason: currently counted as failures but likely out of project scope.
- Requirement: either install/enable `_tkinter` in the probe runtime or explicitly exclude `test_tkinter` via unsupported filters.

4. Implement `Lambda` expression support (`227` tests impacted).
- Reason: high-impact missing expression feature.
- Requirement: support `ast.Lambda` with closure/default binding semantics compatible with existing function call behavior.

5. Fix `from ... import ...` with implicit/relative module contexts (`194` tests impacted).
- Reason: import semantics gap appears directly in `importlib` test families.
- Requirement: support `ImportFrom` where `node.module is None` and ensure relative resolution matches CPython behavior.

6. Reduce runtime timeouts (`177` tests impacted).
- Reason: timeouts hide pass/fail status and slow iteration.
- Requirement: profile top timeout files (`test_asyncio/test_events.py`, `test_queue.py`, `test_sched.py`, `test_thread.py`, `test_zipfile64.py`) and either optimize or isolate pathological paths.

7. Reduce `Suite/Failure` assertion failures (`194` tests impacted).
- Reason: logic-level mismatches after tests execute.
- Requirement: prioritize top files (`test_augassign.py`, `test_codeop.py`, `test_asyncio/test_futures.py`, `test_ctypes/test_struct_fields.py`, `test_dbm_dumb.py`) and align semantics.

8. Triage residual `AttributeError` compatibility gaps (`81` tests impacted).
- Reason: non-sandbox attribute errors indicate missing stdlib/runtime compatibility.
- Requirement: classify and fix recurring attribute contract mismatches (`test`/`unittest` helper expectations, enum/member metadata expectations).

9. Implement `Starred` expression support (`36` tests impacted).
- Requirement: support `ast.Starred` in remaining expression contexts not currently handled.

10. Implement `TypeAlias` statement support (`30` tests impacted).
- Requirement: support `ast.TypeAlias` for 3.14 typing-related tests.

11. SKIP ~~Decide final policy for `__code__` access (`29` tests impacted).~~
- Reason: currently blocked by sandbox guard.
- Requirement: either keep blocked and exclude related tests, or add a constrained capability path if needed for target compatibility.

## Scope note

- Keep unsupported-feature filters explicit and versioned in the probe.
- Do not silently mix environment-missing modules with interpreter semantic failures in progress metrics.
