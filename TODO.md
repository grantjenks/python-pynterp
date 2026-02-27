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
- Progress (2026-02-27, iter 005): Removed shared `tempcwd` probe-worker race by remapping `test.support.os_helper.temp_cwd()` default directory to a PID-scoped name inside the runner (`tempcwd-<pid>`) and cleaning only that worker-local path.
- Local checks: `uv run pytest tests/test_cpython_pynterp_probe.py -k tempcwd -q` => `1 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `5 passed`; targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_tools/test_msgfmt.py`) => `14 run, 0 errors`.
- Expected full-probe delta on next rerun: suite-error signature `FileNotFoundError: [Errno 2] No such file or directory: 'messages.po'` should drop from `15` toward `0` (pending measurement).
- Progress (2026-02-27, iter 006): Mirrored CPython class construction behavior by implicitly wrapping interpreted `__init_subclass__` and `__class_getitem__` hooks as `classmethod` when undecorated in class bodies, preventing missing-`cls` hook invocation errors.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "init_subclass or class_getitem" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -q` => `69 passed, 3 skipped`.
- Expected full-probe delta on next rerun: suite-error signature `TypeError: __init_subclass__() missing required argument 'cls'` should drop from `8` toward `0` (pending measurement).
- Progress (2026-02-27, iter 007): Added function type-parameter materialization on interpreted `UserFunction` objects (`__type_params__` defaults to `()` and is populated for `def f[T](...)`), with regression tests for both non-generic and generic definitions.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "user_function_exposes_empty_type_params or generic_function_records_type_params_without_scope_leak" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "type_params or typealias" -q` => `4 passed`; `uv run pytest tests/test_core_semantics.py -q` => `71 passed, 3 skipped`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `25 -> 19` (`-6`), and suite-error signature `AttributeError: 'UserFunction' object has no attribute '__type_params__'` `7 -> 0`.
- Expected full-probe delta on next rerun: suite-error signature `AttributeError: 'UserFunction' object has no attribute '__type_params__'` should drop from `7` toward `0` (pending measurement).
- Progress (2026-02-27, iter 008): Added class-private attribute name mangling (`__x` -> `_Class__x`) for interpreted class contexts by propagating class ownership into nested function call scopes and applying mangling across attribute load/store/delete/augassign paths.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "class_private_slot_attribute_access_is_name_mangled or init_subclass or class_getitem" -q` => `3 passed`; `uv run pytest tests/test_core_semantics.py -q` => `72 passed, 3 skipped`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `5 passed`.
- Targeted CPython 3.14 diagnostic (`Lib/test/test_binop.py` via interpreter harness): suite `errors` `9 -> 1` (`-8`), and suite-error signature `AttributeError: 'Rat' object has no attribute '__num' and no __dict__ for setting new attributes` `8 -> 0`.
- Expected full-probe delta on next rerun: suite-error signature `AttributeError: 'Rat' object has no attribute '__num' and no __dict__ for setting new attributes` should drop from `8` toward `0` (pending measurement).
- Progress (2026-02-27, iter 009): Added synthetic closure-cell binding for function type parameters in `_make_user_function` (so hidden type-parameter frees resolve/capture correctly), and extended `_TypeAliasEvalScope` to expose type-parameter cells for nested closure capture (e.g., lambda inside alias value/bounds/defaults).
- Local checks: `uv run pytest tests/test_core_semantics.py -k "nested_generic_function_can_capture_outer_type_param or typealias_lambda_can_capture_type_param or generic_function_records_type_params_without_scope_leak" -q` => `3 passed`; `uv run pytest tests/test_core_semantics.py -q` => `74 passed, 3 skipped`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `5 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `19 -> 12` (`-7`); suite-error signatures `NameError: cannot capture 'A': not a cellvar or freevar in this scope` `7 -> 1`, `NameError: cannot capture 'T': not a cellvar or freevar in this scope` `3 -> 1` (combined `10 -> 2`, `-8`).
- Expected full-probe delta on next rerun: suite-error signatures for hidden type-parameter capture (`cannot capture 'A'/'T'`) should decrease materially from the current baseline (pending full-run measurement).
- Progress (2026-02-27, iter 010): Materialized interpreted function `__annotations__` for `def`/`async def`, including generic type-parameter resolution at definition time via `_TypeAliasEvalScope`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "empty_annotations or annotations_capture_type_params" -q` => `2 passed, 77 deselected`; `uv run pytest tests/test_core_semantics.py -q` => `76 passed, 3 skipped`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `12 -> 11` (`-1`); suite-error signature `AttributeError: 'UserFunction' object has no attribute '__annotations__'` `1 -> 0`.
- Expected full-probe delta on next rerun: suite-error signature `AttributeError: 'UserFunction' object has no attribute '__annotations__'` should remain at `0` (pending full-run measurement).
- Progress (2026-02-27, iter 011): Added support for starred type-parameter defaults (e.g., `type Alias[*Ts = *default] = ...`) by evaluating `ast.Starred` defaults with single-target unpack semantics in `_build_type_param`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "typevartuple_default_star_unpack_is_supported or typealias_statement_builds_runtime_alias_with_params" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -q` => `77 passed, 3 skipped` (`+1 passed` vs iter 010 from new regression coverage).
- Expected full-probe delta on next rerun: suite-error signature(s) caused by `NotImplementedError: Expression not supported: Starred` in type-parameter default evaluation should decrease (pending measurement).
- Progress (2026-02-27, iter 012): Added starred class-base unpack support in `ClassDef` evaluation plus generic-class type-parameter wiring (`__type_params__` materialization and automatic `typing.Generic[...]` base synthesis, including `TypeVarTuple` -> `typing.Unpack[...]` expansion for `Generic[...]` compatibility).
- Local checks: `uv run pytest tests/test_core_semantics.py -k "generic_class_with_starred_bases_exposes_type_params or generic_class_with_typevartuple_param_is_subscriptable or starred_generic_alias_class_base_unpacks_and_tracks_orig_bases" -q` => `3 passed`; `uv run pytest tests/test_core_semantics.py -q` => `80 passed, 3 skipped`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `11 -> 7` (`-4`), suite `failures` `6 -> 3` (`-3`); eliminated suite-error signatures `NotImplementedError: Expression not supported: Starred` (`1 -> 0`), `ValueError: not enough values to unpack (expected 1, got 0)` (`2 -> 0`), and `TypeError: type 'Class1'/'NewStyle' is not subscriptable` (`2 -> 0` combined).
- Expected full-probe delta on next rerun: suite errors tied to generic class base handling and missing class type-parameter wiring should decrease measurably (pending full-run measurement).
- Progress (2026-02-27, iter 013): Added class-body type-parameter cells in `ClassBodyScope` (with CPython-like shadowing on class-local rebinding) and threaded them through `ClassDef` execution paths so closures/lambdas/method bodies inside generic classes can capture outer class type params.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "generic_class_type_param_is_visible_in_body_and_method_closure or typealias_lambda_in_generic_class_captures_class_type_param or generic_typealias_lambda_in_generic_class_captures_outer_type_param" -q` => `3 passed`; `uv run pytest tests/test_core_semantics.py -q` => `83 passed, 3 skipped` (`+3 passed` vs iter 012 from new regression coverage).
- Expected full-probe delta on next rerun: suite-error signatures like `NameError: cannot capture free variable 'T'/'U' from module scope` in generic class alias/lambda/method closure scenarios should decrease (pending full-run measurement).
- Progress (2026-02-27, iter 014): Updated nested class name resolution in `ClassBodyScope` so inner class bodies skip outer class locals while still seeing outer class type-parameter cells (CPython-compatible in `test_type_params`-style nested class cases).
- Local checks: `uv run pytest tests/test_core_semantics.py -k "nested_class_body_skips_outer_class_locals_for_name_loads or nested_class_body_prefers_outer_type_params_over_shadowed_class_name" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "nested_class_body or generic_class_type_param_is_visible_in_body_and_method_closure or typealias_lambda_in_generic_class_captures_class_type_param or generic_typealias_lambda_in_generic_class_captures_outer_type_param" -q` => `5 passed`.
- Expected full-probe delta on next rerun: nested `test_type_params` suite errors/failures caused by leaking outer class locals into inner class bodies (e.g., inner class `x = T` resolving to class-local `T` instead of enclosing function/type-parameter bindings) should decrease (pending measurement).
- Progress (2026-02-27, iter 015): Added type-parameter binding aliases for class-private mangled names (e.g., `__T`/`__U` alongside `_Foo__T`/`_Foo__U`) across class/function/type-alias paths, and seeded provisional current-type-param bindings during bound/constraint/default evaluation so comprehension-heavy self references no longer resolve as unbound locals.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "typealias_constraint_comprehension_sees_current_type_param or generic_method_private_type_param_capture_uses_mangled_name" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "nested_class_body or generic_class_type_param_is_visible_in_body_and_method_closure or typealias_lambda_in_generic_class_captures_class_type_param or generic_typealias_lambda_in_generic_class_captures_outer_type_param or typealias_constraint_comprehension_sees_current_type_param or generic_method_private_type_param_capture_uses_mangled_name" -q` => `7 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `5 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `6 -> 3` (`-3`), suite `failures` `3 -> 6` (`+3`); eliminated suite-error signatures `UnboundLocalError: local variable 'T' referenced before assignment` (`3 -> 0`) and `NameError: cannot capture '_Foo__U': not a cellvar or freevar in this scope` (`1 -> 0`).
- Expected full-probe delta on next rerun: `Suite/Error` signatures for type-param self-reference comprehensions and mangled method type-param capture should decrease; remaining `test_type_params` errors are now concentrated in lazy bound/constraint evaluation (`Foo`/`Undefined`) and class-private name loads in method bodies (`NameError: __T`).
- Progress (2026-02-27, iter 016): Applied class-private name mangling to `Name` load evaluation paths (`eval_Name` and `g_eval_Name`) so method/runtime lookups resolve CPython-mangled free variables (e.g., `_Foo__T`) instead of raw `__T`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "generic_method_private_type_param_capture_uses_mangled_name or generic_method_body_private_type_params_resolve_in_runtime_scope" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "typealias_constraint_comprehension_sees_current_type_param or generic_method_private_type_param_capture_uses_mangled_name or generic_method_body_private_type_params_resolve_in_runtime_scope" -q` => `3 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `3 -> 2` (`-1`), suite `failures` unchanged at `6`; eliminated suite-error signature `NameError: __T` (`1 -> 0`).
- Expected full-probe delta on next rerun: remaining `test_type_params` suite errors are concentrated in lazy bound/constraint evaluation (`UnboundLocalError` for `Foo`/`Undefined`) and should decrease with lazy-evaluation scope fixes.
- Progress (2026-02-27, iter 017): Added lazy fallback construction for interpreted `TypeVar` bounds/constraints when name resolution is deferred (using compiler-generated type-parameter evaluators), so recursive/self-referential and late-bound names no longer fail class definition eagerly.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "generic_class_typevar_bounds_are_lazily_evaluated or generic_class_typevar_lazy_name_errors_can_resolve_later" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "generic_method_private_type_param_capture_uses_mangled_name or generic_method_body_private_type_params_resolve_in_runtime_scope or typealias_constraint_comprehension_sees_current_type_param" -q` => `3 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_type_params.py`): suite `errors` `2 -> 0` (`-2`), suite `failures` unchanged at `6`; eliminated suite-error signatures `UnboundLocalError: local variable 'Foo' referenced before assignment` (`1 -> 0`) and `UnboundLocalError: local variable 'Undefined' referenced before assignment` (`1 -> 0`).
- Expected full-probe delta on next rerun: `Suite/Error` should no longer include `test_type_params` lazy bound/constraint initialization crashes (`Foo`/`Undefined`).
- Progress (2026-02-27, iter 018): Reworked guarded attribute loading so `__getattribute__` returns a sandboxed callable (instead of hard blocking), with a safe `object.__getattribute__` static-lookup fallback to avoid recursion in interpreted `__getattribute__` methods; also switched `FunctionScope.load()` cell checks from `isinstance(val, Cell)` to `type(val) is Cell` to prevent recursive `__getattribute__` re-entry during local-name loads.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "getattribute" -q` => `2 passed`; `uv run pytest tests/test_core_semantics.py -k "attr_guard or object_getattribute_delegate" -q` => `7 passed`; `uv run pytest tests/test_sandbox_security.py -q` => `4 passed`.
- Targeted CPython 3.14 diagnostics (`run_case`): `Lib/test/test_asyncio/test_futures.py` suite `errors` `9 -> 3` (`-6`), eliminating suite-error signature `AttributeError: attribute access to '__getattribute__' is blocked in this environment` (`6 -> 0`) while leaving the existing `ValueError: unable to get the source of <UserFunction _fakefunc (func)>` (`3`) unchanged; `Lib/test/test_minidom.py` suite `errors` `1 -> 0` (`-1`), eliminating the same blocked-`__getattribute__` signature (`1 -> 0`).
- Expected full-probe delta on next rerun: suite-error signature `AttributeError: attribute access to '__getattribute__' is blocked in this environment` should decrease from baseline `7` toward `0`; overall `Suite/Error` should drop by at least `7` from this slice (pending full-run measurement).
- Progress (2026-02-27, iter 019): Added runtime compat patching for `asyncio.format_helpers._get_function_source` so interpreted `UserFunction` callbacks resolve `(filename, lineno)` like native functions; this targets the remaining `ValueError: unable to get the source of <UserFunction _fakefunc (func)>` signature from `test_asyncio/test_futures.py` diagnostics.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "asyncio_format_helpers_resolves_user_function_source" -q` => `1 passed` (new regression); `uv run pytest tests/test_core_semantics.py -k "importlib_metadata_available_without_importlib_import_module or import_dotted_module_as_alias_binds_leaf_module or import_dotted_module_without_alias_binds_top_level_name" -q` => `3 passed`; `uv run pytest tests/test_sandbox_security.py -q` => `4 passed`.
- Auxiliary CPython 3.14.2 stdlib diagnostic (`run_case` on installed test tree `test_asyncio/test_futures.py`): suite `errors` now `0`, with no suite-error signatures reported in the case payload.
- Expected full-probe delta on next rerun: remaining `Suite/Error` signature `ValueError: unable to get the source of <UserFunction _fakefunc (func)>` should decrease from the prior targeted diagnostic level (`3`) toward `0` (pending full-run measurement on canonical baseline tree).
- Progress (2026-02-27, iter 020): Hardened `_call_user_function` against host builtins rebinding by using stable builtin snapshots for call-binding/runtime plumbing (`len`, `zip`, `any`, `hasattr`, `next`, `tuple`, `isinstance`), preventing recursive self-reentry when `builtins.len` is temporarily replaced with an interpreted `UserFunction`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "survives_builtin_len_rebind" -q` => `1 passed` (new regression for host `builtins.len` rebound to `UserFunction`); `uv run pytest tests/test_core_semantics.py -k "lambda_missing_required_argument_name or survives_builtin_len_rebind" -q` => `2 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_dynamic.py`): suite `errors` `3 -> 1` (`-2`), and suite-error signature `RecursionError: maximum recursion depth exceeded` `3 -> 0` (remaining suite error now `IndexError: list index out of range` `1`).
- Expected full-probe delta on next rerun: `Suite/Error` recursion-signature counts should drop by at least the prior `test_dynamic.py` contribution (`-3`), with remaining recursion signatures currently concentrated in `test_fstring.py` (`1`) and `test_tomllib/test_misc.py` (`2`) based on targeted reruns.
- Progress (2026-02-27, iter 021): Switched probe-runner module env to live `builtins` (`__builtins__ = builtins`) and added interpreted `globals()` dispatch in call evaluation (normal + generator paths), so runtime builtins/global rebinding follows CPython `test_dynamic` expectations.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "globals_builtin_returns_interpreted_module_namespace or survives_builtin_len_rebind" -q` => `2 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -k "live_builtins_for_rebinding or run_case_normalizes_sysconf_permission_error" -q` => `2 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_dynamic.py`): suite `errors` `1 -> 0` (`-1`), suite `failures` `3 -> 0` (`-3`); eliminated suite-error signature `IndexError: list index out of range` (`1 -> 0`).
- Expected full-probe delta on next rerun: `Suite/Error` should drop by at least `1` from the prior `test_dynamic.py` contribution, and `Suite/Failure` should decrease by at least `3` from the same module slice.
- Progress (2026-02-27, iter 022): Added interpreted `exec()`/`eval()` default-scope dispatch (normal + generator call paths) so calls without explicit globals/locals execute against interpreted module/function scope instead of host frame locals, and added a symtable construction fallback for CPython `Lib/symtable.py` variants that pass unsupported keyword args to host `_symtable`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "globals_builtin_returns_interpreted_module_namespace or exec_builtin_uses_interpreted_function_scope_locals or eval_builtin_uses_interpreted_function_scope_locals or module_code_handles_symtable_keyword_incompatibility" -q` => `4 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `6 passed`.
- Targeted CPython 3.14 diagnostic (`run_case`): `Lib/test/test_fstring.py` suite `errors` `4 -> 1` (`-3`), eliminating suite-error signature `NameError: name 'x' is not defined` (`3 -> 0`) and leaving `RecursionError: maximum recursion depth exceeded` (`1`) unchanged; `Lib/test/test_tomllib/test_misc.py` remains `errors: 2` (`RecursionError` signatures unchanged).
- Expected full-probe delta on next rerun: `Suite/Error` should decrease by at least `3` from the `test_fstring.py` `exec`/`eval` local-scope mismatch slice.
- Progress (2026-02-27, iter 023): Added adaptive recursion-limit headroom during interpreted calls (normal/generator/async + interpreted-to-native call sites), with root-call restoration to avoid leaking automatic recursion-limit bumps after interpreted execution.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "recursive_user_function_can_build_deep_fstring_shape or survives_builtin_len_rebind or globals_builtin_returns_interpreted_module_namespace" -q` => `3 passed`; `uv run pytest tests/test_core_semantics.py -k "exec_builtin_uses_interpreted_function_scope_locals or eval_builtin_uses_interpreted_function_scope_locals" -q` => `2 passed`; `uv run pytest tests/test_sandbox_security.py -q` => `4 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `6 passed`.
- Targeted CPython 3.14 diagnostics (`run_case`): `Lib/test/test_fstring.py` suite `errors` `1 -> 0` (`-1`) with suite `failures` unchanged at `1`; `Lib/test/test_tomllib/test_misc.py` suite `errors` `2 -> 0` (`-2`), eliminating remaining `RecursionError: maximum recursion depth exceeded` suite-error signatures in both modules.
- Expected full-probe delta on next rerun: `Suite/Error` recursion-signature counts should decrease by at least `3` from the prior `test_fstring.py` + `test_tomllib/test_misc.py` targeted baseline.
- Progress (2026-02-27, iter 024): Implemented `raise ... from ...` semantics in both statement execution paths (`exec_Raise` and `g_exec_Raise`), including cause-type validation (`TypeError: exception causes must derive from BaseException`) and class-cause instantiation behavior.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "raise_from_none_suppresses_context or raise_from_invalid_cause_raises_typeerror or raise_from_class_cause_sets_exception_cause or raise_from_invalid_cause_in_generator_path or bare_raise_reraises_caught_exception or bare_raise_without_active_exception_raises_runtimeerror" -q` => `7 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `6 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_raise.py`): suite `errors` `8 -> 5` (`-3`) and `failures` `3 -> 1` (`-2`), eliminating suite-error signature `IndexError` (`3 -> 0`); remaining suite errors are now `tb_next` sandbox blocks (`3`) and nested re-raise context handling (`RuntimeError: No active exception to reraise`, `TypeError: foo`).
- Expected full-probe delta on next rerun: suite-error signature `IndexError` from `Lib/test/test_raise.py` should decrease by at least `3` versus the current baseline (pending full-run measurement).
- Progress (2026-02-27, iter 025): Fixed active-exception propagation for bare `raise` across nested interpreted calls and `try/except/finally` finalizers (normal + generator paths): call scopes now inherit caller `active_exception`, and `exec_Try`/`g_exec_Try` keep the in-flight exception visible to `finally` while still clearing it for handler control-flow exits (`return`/`break`/`continue`).
- Local checks: `uv run pytest tests/test_core_semantics.py -k "nested_function_bare_raise_reraises_caught_exception or bare_raise_in_finally_reraises_current_try_exception or bare_raise_in_finally_after_except_return_has_no_active_exception or bare_raise_reraises_caught_exception or raise_from_none_suppresses_context or raise_from_invalid_cause_raises_typeerror or raise_from_class_cause_sets_exception_cause or raise_from_invalid_cause_in_generator_path" -q` => `9 passed`; `uv run pytest tests/test_core_semantics.py -k "raise" -q` => `11 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `6 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_raise.py`): suite `errors` `5 -> 3` (`-2`) with `failures` unchanged at `1`; eliminated suite-error signatures `RuntimeError: No active exception to reraise` (`1 -> 0`) and `TypeError: foo` (`1 -> 0`), leaving only policy-blocked `tb_next` attribute errors (`3`).
- Expected full-probe delta on next rerun: `Suite/Error` should drop by at least `2` from this `test_raise.py` slice, with residual `tb_next` errors attributable to existing traceback sandbox policy.
- Progress (2026-02-27, iter 026): Relaxed traceback chaining guard by allowing `tb_next` access (while keeping `tb_frame` blocked), and added regression coverage for traceback-chain traversal via `tb_next`.
- Local checks: `uv run pytest tests/test_core_semantics.py -k "attr_guard_allows_traceback_but_keeps_tb_frame_blocked or attr_guard_allows_traceback_chain_navigation_with_tb_next or raise" -q` => `13 passed, 97 deselected`; `uv run pytest tests/test_sandbox_security.py -q` => `4 passed`; `uv run pytest tests/test_cpython_pynterp_probe.py -q` => `6 passed`.
- Targeted CPython 3.14 diagnostic (`run_case` on `Lib/test/test_raise.py`): suite `errors` `3 -> 2` (`-1`) and `failures` `1 -> 2` (`+1`); eliminated suite-error signature `AttributeError: attribute access to 'tb_next' is blocked in this environment` (`3 -> 0`), with residual suite-error signature now `AttributeError: attribute access to 'tb_frame' is blocked in this environment` (`2`).
- Expected full-probe delta on next rerun: suite-error signature `... 'tb_next' is blocked ...` should drop to `0`; net `Suite/Error` change from this slice is currently `-1` on targeted `test_raise.py` diagnostics, with remaining traceback-introspection errors now concentrated on policy-blocked `tb_frame`.

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
