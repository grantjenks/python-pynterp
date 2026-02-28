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
- Progress (2026-02-28, iteration 12): added reflective import-boundary regressions for `super(...).__getattribute__` importer `__self__` pivots plus `type.__getattribute__`/`super(...).__getattribute__` module `__spec__`/`__loader__` metadata access attempts.
- Progress (2026-02-28, iteration 13): added frame-pivot regressions that assert blocked frame internals stay blocked when accessed through `type.__getattribute__` and `super(...).__getattribute__` on coroutine/async-generator/traceback objects.
- Progress (2026-02-28, iteration 14): added class-hierarchy pivot regressions for blocked `__base__` access through direct attribute lookup plus reflective `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths.
- Progress (2026-02-28, iteration 15): added reflective closure/cell regressions that keep `__closure__` blocked through `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` lookup paths.
- Progress (2026-02-28, iteration 16): added class-hierarchy pivot regressions for blocked `__bases__` access through direct lookup and reflective `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths; tightened guard policy to block `__bases__` and aligned attr-guard core semantics coverage.
- Progress (2026-02-28, iteration 17): added reflective `__subclasses__` regressions to ensure class hierarchy pivots stay blocked through `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths.
- Progress (2026-02-28, iteration 18): added reduction-hook regressions for reflective `type.__getattribute__` and `super(...).__getattribute__` paths to keep `__reduce_ex__`/`__reduce__` blocked outside direct and `object.__getattribute__` probes.
- Progress (2026-02-28, iteration 19): added class-hierarchy regressions for blocked `__mro__` access through reflective `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths.
- Progress (2026-02-28, iteration 20): added function `__code__` regressions for direct access and reflective `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths to keep code-object pivots blocked.
- Progress (2026-02-28, iteration 21): added function/importer `__globals__` regressions covering direct and `super(...).__getattribute__` access on user functions plus `__import__.__func__` and reflective `object.__getattribute__` chains.
- Progress (2026-02-28, iteration 22): added importer `__func__.__globals__` regressions for reflective `type(...).__getattribute__` and `super(...).__getattribute__` paths to keep function-global pivots blocked beyond direct and `object.__getattribute__` probes.
- Progress (2026-02-28, iteration 23): added mutator-dunder regressions for blocked `__setattr__` and `__delattr__` access through direct lookup plus reflective `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` paths.
- Progress (2026-02-28, iteration 24): added traceback `f_back` pivot-chain regressions for direct frame walking plus reflective `object.__getattribute__` and instance-type `__getattribute__` descriptor paths, ensuring frame-back traversal still fails safely when probing blocked frame globals/builtins/locals.
- Progress (2026-02-28, iteration 25): closed a reflective guard bypass where stateful `str` subclasses could evade blocked-attribute checks; normalized attribute names before guard enforcement and added regressions for `getattr`, `object.__getattribute__`, and `super(...).__getattribute__` attempts to recover `__import__.__self__`.
- Progress (2026-02-28, iteration 26): closed a reflective guard bypass where `str` subclasses overriding `__str__` could smuggle blocked names through `type(...).__getattribute__` and `super(...).__getattribute__`; normalized forwarded descriptor-call names and added importer `__self__` regression coverage for both reflective paths.
- Progress (2026-02-28, iteration 27): added reflective `str`-subclass regressions for function `__globals__` pivots through `object.__getattribute__`, `type(...).__getattribute__`, and `super(...).__getattribute__`, ensuring blocked-name normalization is enforced beyond importer `__self__` probes.
- Progress (2026-02-28, iteration 28): added keyword-argument reflective getter regressions for importer `__self__` pivots (`object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__`) and closed a `str.__str__`-override normalization gap by canonicalizing `str` subclasses with `str.__str__` before guard checks.
- Progress (2026-02-28, iteration 29): added import-metadata smuggling regressions for `math.__loader__`/`math.__spec__` using stateful `str` subclasses and `str.__str__`-override names across `getattr`, `type.__getattribute__`, and `super(...).__getattribute__` lookup paths.
- Progress (2026-02-28, iteration 30): added reflective generator-frame regressions for `type.__getattribute__` and `super(...).__getattribute__` `gi_frame` pivots, plus a stateful `str` subclass keyword-name bypass attempt for `type.__getattribute__(..., name=...)`.
- Progress (2026-02-28, iteration 31): added keyword-name import-metadata regressions for module `__loader__`/`__spec__` pivots using `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` with stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 32): added keyword-name frame-internal regressions for traceback/coroutine pivots, covering `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` with stateful `str` subclasses and `str.__str__` overrides targeting `f_globals`/`f_builtins`/`f_locals`.
- Progress (2026-02-28, iteration 33): added keyword-name function-`__globals__` regressions that exercise `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` with stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 34): added module-`__dict__` import-smuggling regressions covering direct access, `object.__getattribute__`, and keyword-name `type.__getattribute__` with a stateful `str` subclass.
- Progress (2026-02-28, iteration 35): added module-`__dict__` reflective regressions for `super(...).__getattribute__` direct access plus keyword-name `object.__getattribute__`/`super(...).__getattribute__` probes using `str.__str__`-override subclasses.
- Progress (2026-02-28, iteration 36): added builtin-callable `__self__` reflective regressions for missing `super(...).__getattribute__` and keyword-name `object.__getattribute__`/`type.__getattribute__` probes (including a stateful `str` subclass) to keep host `builtins` module recovery blocked.
- Progress (2026-02-28, iteration 37): added builtin-callable `__self__` keyword-name regressions for missing `super(...).__getattribute__` probes, including stateful `str`-subclass and `str.__str__`-override bypass attempts, to ensure keyword dispatch cannot recover host `builtins`.
- Progress (2026-02-28, iteration 38): expanded module-`__dict__` escape coverage with missing `type.__getattribute__` direct access and keyword-name bypass probes across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` using both stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 39): added class-`__subclasses__` keyword-name bypass regressions across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` using stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 40): added class-`__mro__` keyword-name bypass regressions across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` using stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 41): added blocked-`__getattr__` regressions for direct access, reflective `object.__getattribute__`/`type.__getattribute__`/`super(...).__getattribute__` lookups, and keyword-name bypass probes using stateful `str` subclasses and `str.__str__` overrides.
- Progress (2026-02-28, iteration 42): added bound/super `__getattribute__` keyword-name regressions for blocked `__dict__` access, including stateful `str` subclasses and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 43): added traceback-frame bound-`__getattribute__` keyword-name regressions for blocked `f_globals`/`f_builtins` access, including stateful `str` subclasses and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 44): added traceback-frame bound-`__getattribute__` keyword-name regressions for blocked `f_locals` access, covering direct probes plus stateful `str` subclass and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 45): added coroutine-frame bound-`__getattribute__` keyword-name regressions for blocked `f_globals`/`f_builtins`/`f_locals` access, covering direct probes plus stateful `str` subclass and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 46): added async-generator-frame bound-`__getattribute__` keyword-name regressions for blocked `f_globals`/`f_builtins`/`f_locals` access, covering direct probes plus stateful `str` subclass and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 47): added generator-frame bound-`__getattribute__` keyword-name regressions for blocked `f_globals`/`f_builtins`/`f_locals` access, covering direct probes plus stateful `str` subclass and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 48): added blocked-generator-`gi_frame` keyword-name regressions for bound `__getattribute__`, `object.__getattribute__` with stateful `str` subclasses, and `super(...).__getattribute__` with `str.__str__` overrides.
- Progress (2026-02-28, iteration 49): added module-metadata bound-`__getattribute__` keyword-name regressions for blocked `__loader__`/`__spec__` access, including stateful `str` subclass and `str.__str__`-override bypass attempts.
- Progress (2026-02-28, iteration 50): expanded module-`__dict__` bound-`__getattribute__` keyword-name regressions, adding direct probes plus stateful `str` subclass and `str.__str__`-override bypass attempts.
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
- Metrics: `tests/test_sandbox_security.py` cases 38 -> 41 (+3). Validation gates this iteration: `41 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 41 -> 45 (+4). Validation gates this iteration: `45 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 45 -> 49 (+4). Validation gates this iteration: `49 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 49 -> 52 (+3). Validation gates this iteration: `52 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 52 -> 56 (+4). Validation gates this iteration: `56 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 56 -> 59 (+3). Validation gates this iteration: `59 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 59 -> 63 (+4). Validation gates this iteration: `63 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 63 -> 66 (+3). Validation gates this iteration: `66 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 66 -> 70 (+4). Validation gates this iteration: `70 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 70 -> 74 (+4). Validation gates this iteration: `74 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 74 -> 76 (+2). Validation gates this iteration: `76 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 76 -> 84 (+8). Validation gates this iteration: `84 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 84 -> 87 (+3). Validation gates this iteration: `87 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 87 -> 90 (+3). Validation gates this iteration: `90 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 90 -> 92 (+2). Validation gates this iteration: `92 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 92 -> 95 (+3). Validation gates this iteration: `95 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 95 -> 98 (+3). Validation gates this iteration: `98 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 98 -> 101 (+3). Validation gates this iteration: `101 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 101 -> 104 (+3). Validation gates this iteration: `104 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 104 -> 107 (+3). Validation gates this iteration: `107 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 107 -> 110 (+3). Validation gates this iteration: `110 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 110 -> 113 (+3). Validation gates this iteration: `113 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 113 -> 116 (+3). Validation gates this iteration: `116 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 116 -> 119 (+3). Validation gates this iteration: `119 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 119 -> 122 (+3). Validation gates this iteration: `122 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 122 -> 125 (+3). Validation gates this iteration: `125 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 125 -> 129 (+4). Validation gates this iteration: `129 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 129 -> 132 (+3). Validation gates this iteration: `132 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 132 -> 135 (+3). Validation gates this iteration: `135 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 135 -> 142 (+7). Validation gates this iteration: `142 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 142 -> 146 (+4). Validation gates this iteration: `146 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 146 -> 149 (+3). Validation gates this iteration: `149 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 149 -> 152 (+3). Validation gates this iteration: `152 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 152 -> 155 (+3). Validation gates this iteration: `155 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 155 -> 158 (+3). Validation gates this iteration: `158 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 158 -> 161 (+3). Validation gates this iteration: `161 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 161 -> 164 (+3). Validation gates this iteration: `164 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 164 -> 167 (+3). Validation gates this iteration: `167 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Metrics: `tests/test_sandbox_security.py` cases 167 -> 170 (+3). Validation gates this iteration: `170 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 51): added module-metadata bound-`__getattribute__` regressions for a missing direct `__spec__` keyword-name probe and complementary bypass attempts (`__loader__` via stateful `str` subclass, `__spec__` via `str.__str__` override).
- Metrics: `tests/test_sandbox_security.py` cases 170 -> 173 (+3). Validation gates this iteration: `173 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 52): added positional-name bound-`__getattribute__` regressions for module metadata pivots, covering `math.__getattribute__(name)` with hostile `str` subclasses (`__loader__`, `__dict__`, `__spec__`) to mirror existing keyword-name bypass coverage.
- Metrics: `tests/test_sandbox_security.py` cases 173 -> 176 (+3). Validation gates this iteration: `176 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 53): added keyword-key (`**{key: ...}`) bound/super `__getattribute__` regressions for module metadata pivots and hardened guarded `__getattribute__` dispatch to canonicalize hostile `str`-subclass `name` keyword keys before blocked-attribute enforcement.
- Metrics: `tests/test_sandbox_security.py` cases 176 -> 179 (+3). Validation gates this iteration: `179 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 54): added keyword-key (`**{key: ...}`) frame-pivot regressions for bound/super `__getattribute__` dispatch across traceback/generator/coroutine frames, covering blocked `f_globals`, `f_locals`, and `f_builtins` targets.
- Metrics: `tests/test_sandbox_security.py` cases 179 -> 182 (+3). Validation gates this iteration: `182 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 55): added keyword-key (`**{key: ...}`) regressions for missing `object.__getattribute__` and `type.__getattribute__` dispatch paths, covering traceback/generator frame pivots and module `__loader__` metadata access attempts.
- Metrics: `tests/test_sandbox_security.py` cases 182 -> 185 (+3). Validation gates this iteration: `185 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 56): added keyword-key (`**{key: ...}`) regressions for importer/builtin `__self__` and function `__globals__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 185 -> 188 (+3). Validation gates this iteration: `188 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 57): added keyword-key (`**{key: ...}`) class-hierarchy regressions for blocked `__base__`/`__bases__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 188 -> 191 (+3). Validation gates this iteration: `191 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 58): added keyword-key (`**{key: ...}`) class-hierarchy regressions for blocked `__subclasses__`/`__mro__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 191 -> 197 (+6). Validation gates this iteration: `197 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 59): added keyword-key (`**{key: ...}`) reduction-hook regressions for blocked `__reduce__`/`__reduce_ex__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 197 -> 200 (+3). Validation gates this iteration: `200 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 60): added keyword-key (`**{key: ...}`) closure/cell regressions for blocked `__closure__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 200 -> 203 (+3). Validation gates this iteration: `203 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 61): added keyword-key (`**{key: ...}`) function-code regressions for blocked `__code__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 203 -> 206 (+3). Validation gates this iteration: `206 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 62): added complementary keyword-key function-code regressions for blocked `__code__` pivots, covering the remaining hostile-name combinations (`str.__str__` override via `object.__getattribute__`/`super(...).__getattribute__`, and stateful `str` subclass via `type.__getattribute__`).
- Metrics: `tests/test_sandbox_security.py` cases 206 -> 209 (+3). Validation gates this iteration: `209 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 63): added keyword-key function-`__globals__` regressions for blocked builtins pivots using stateful `str` subclasses across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 209 -> 212 (+3). Validation gates this iteration: `212 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 64): added keyword-key (`**{key: ...}`) regressions for blocked `__setattr__`, `__delattr__`, and `__getattr__` pivots across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 212 -> 215 (+3). Validation gates this iteration: `215 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 65): added keyword-key (`**{key: ...}`) regressions for the `__import__.__func__.__globals__` escape chain across `object.__getattribute__`, `type.__getattribute__`, and `super(...).__getattribute__` dispatch paths.
- Metrics: `tests/test_sandbox_security.py` cases 215 -> 218 (+3). Validation gates this iteration: `218 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 66): added metaclass `__getattribute__` regressions for blocked `__subclasses__` pivots via hostile keyword dispatch, covering stateful `str`-subclass and `str.__str__`-override keyword-name probes plus a stateful keyword-key (`**{key: ...}`) bypass attempt.
- Metrics: `tests/test_sandbox_security.py` cases 218 -> 221 (+3). Validation gates this iteration: `221 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 67): added metaclass `__getattribute__` regressions for blocked `__mro__` pivots, covering direct access plus hostile keyword-name and keyword-key (`**{key: ...}`) dispatch attempts with stateful `str` subclasses.
- Metrics: `tests/test_sandbox_security.py` cases 221 -> 224 (+3). Validation gates this iteration: `224 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 68): added metaclass `__getattribute__` regressions for blocked `__bases__` pivots, covering direct access plus hostile keyword-name and keyword-key (`**{key: ...}`) dispatch attempts with stateful `str` subclasses.
- Metrics: `tests/test_sandbox_security.py` cases 224 -> 227 (+3). Validation gates this iteration: `227 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 69): added metaclass `__getattribute__` regressions for blocked `__base__` pivots, covering direct access plus hostile keyword-name and keyword-key (`**{key: ...}`) dispatch attempts with stateful `str` subclasses.
- Metrics: `tests/test_sandbox_security.py` cases 227 -> 230 (+3). Validation gates this iteration: `230 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 70): added metaclass `__getattribute__` regressions for blocked `__mro__`, `__bases__`, and `__base__` pivots using `str.__str__`-override keyword-name probes.
- Metrics: `tests/test_sandbox_security.py` cases 230 -> 233 (+3). Validation gates this iteration: `233 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 71): added metaclass `__getattribute__` regressions for blocked `__subclasses__`, `__mro__`, `__bases__`, and `__base__` pivots using `str.__str__`-override keyword-key (`**{key: ...}`) dispatch probes.
- Metrics: `tests/test_sandbox_security.py` cases 233 -> 237 (+4). Validation gates this iteration: `237 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 72): added metaclass `__getattribute__` regressions for hostile positional-name dispatch using `str.__str__`-override subclasses across blocked `__subclasses__`, `__mro__`, `__bases__`, and `__base__` pivots.
- Metrics: `tests/test_sandbox_security.py` cases 237 -> 241 (+4). Validation gates this iteration: `241 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 73): added metaclass `__getattribute__` regressions for hostile positional-name dispatch using stateful `str` subclasses across blocked `__subclasses__`, `__mro__`, `__bases__`, and `__base__` pivots.
- Metrics: `tests/test_sandbox_security.py` cases 241 -> 245 (+4). Validation gates this iteration: `245 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 74): added bound-callable `__getattribute__` regressions for builtin/importer `__self__` pivots (`len.__getattribute__` and `__import__.__getattribute__`), including stateful `str`-subclass keyword-key (`**{key: ...}`) bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 245 -> 249 (+4). Validation gates this iteration: `249 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 75): added bound-callable `__getattribute__` keyword-name regressions for builtin/importer `__self__` pivots (`len.__getattribute__` and `__import__.__getattribute__`), covering direct `name="__self__"` probes plus stateful `str`-subclass and `str.__str__`-override bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 249 -> 255 (+6). Validation gates this iteration: `255 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 76): added bound-callable `__getattribute__` positional-name regressions for builtin/importer `__self__` pivots (`len.__getattribute__(name)` and `__import__.__getattribute__(name)`), covering both stateful `str`-subclass and `str.__str__`-override bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 255 -> 259 (+4). Validation gates this iteration: `259 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 77): added bound-callable function `__getattribute__` regressions for blocked `__globals__` pivots (`probe.__getattribute__`), covering direct access plus hostile stateful `str`-subclass keyword-name and `str.__str__`-override keyword-key bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 259 -> 262 (+3). Validation gates this iteration: `262 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 78): added bound-callable function `__getattribute__` positional-name regressions for blocked `__globals__` pivots (`probe.__getattribute__(name)`), covering hostile stateful `str`-subclass and `str.__str__`-override bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 262 -> 264 (+2). Validation gates this iteration: `264 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 79): added bound-callable function `__getattribute__` regressions for blocked `__code__` pivots (`f.__getattribute__`), covering direct access plus hostile positional-name, keyword-name, and keyword-key bypass attempts via stateful `str` subclasses and `str.__str__` overrides.
- Metrics: `tests/test_sandbox_security.py` cases 264 -> 269 (+5). Validation gates this iteration: `269 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 80): added bound-callable function `__getattribute__` regressions for blocked closure-cell pivots (`fn.__getattribute__` on `__closure__`), covering direct access plus hostile positional-name, keyword-name, and keyword-key bypass attempts via stateful `str` subclasses and `str.__str__` overrides.
- Metrics: `tests/test_sandbox_security.py` cases 269 -> 274 (+5). Validation gates this iteration: `274 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 81): added bound-callable object `__getattribute__` regressions for blocked reduction-hook pivots (`target.__getattribute__` on `__reduce__`/`__reduce_ex__`), covering direct access plus hostile positional-name, keyword-name, and keyword-key bypass attempts via stateful `str` subclasses and `str.__str__` overrides.
- Metrics: `tests/test_sandbox_security.py` cases 274 -> 278 (+4). Validation gates this iteration: `278 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 82): added bound-callable function `__getattribute__` regressions for blocked `__globals__` pivots (`probe.__getattribute__`), covering missing direct keyword-name plus hostile `str.__str__`-override keyword-name and stateful `str`-subclass keyword-key bypass attempts.
- Metrics: `tests/test_sandbox_security.py` cases 278 -> 281 (+3). Validation gates this iteration: `281 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 83): added descriptor-abuse regressions for guarded bound `__getattribute__` callables rebound via `.__get__(None, type(...))`, covering blocked function `__globals__`, importer `__self__`, and module `__loader__` pivots.
- Metrics: `tests/test_sandbox_security.py` cases 281 -> 284 (+3). Validation gates this iteration: `284 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 84): expanded descriptor-rebound bound-`__getattribute__` regressions with hostile dispatch variants, adding keyword-name function-`__globals__`, stateful keyword-key importer-`__self__`, and `str.__str__`-override positional module-`__loader__` probes.
- Metrics: `tests/test_sandbox_security.py` cases 284 -> 287 (+3). Validation gates this iteration: `287 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 85): expanded descriptor-rebound bound-`__getattribute__` regressions for additional blocked pivots, adding builtin `len.__self__` coverage plus hostile dispatch probes for builtin `__self__` (keyword-name `str.__str__` override) and module `__spec__` (stateful keyword-key).
- Metrics: `tests/test_sandbox_security.py` cases 287 -> 290 (+3). Validation gates this iteration: `290 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 86): expanded descriptor-rebound bound-`__getattribute__` regressions to traceback-frame pivots, adding blocked `f_globals` coverage plus hostile dispatch probes for `f_locals` (keyword-name `str.__str__` override) and `f_builtins` (stateful keyword-key).
- Metrics: `tests/test_sandbox_security.py` cases 290 -> 293 (+3). Validation gates this iteration: `293 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 87): expanded descriptor-rebound bound-`__getattribute__` regressions to coroutine/async-generator frame pivots, adding blocked `f_globals` coverage plus hostile dispatch probes for coroutine-frame `f_locals` (keyword-name `str.__str__` override) and async-generator-frame `f_builtins` (stateful keyword-key).
- Metrics: `tests/test_sandbox_security.py` cases 293 -> 296 (+3). Validation gates this iteration: `296 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 88): expanded descriptor-rebound bound-`__getattribute__` regressions to generator-frame pivots, adding blocked `f_globals` coverage plus hostile dispatch probes for `f_locals` (keyword-name `str.__str__` override) and `f_builtins` (stateful keyword-key).
- Metrics: `tests/test_sandbox_security.py` cases 296 -> 299 (+3). Validation gates this iteration: `299 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 89): expanded descriptor-rebound bound-`__getattribute__` regressions to async-generator frame pivots, adding missing blocked `f_globals` direct coverage and hostile keyword-name `f_locals` probes via `str.__str__`-override subclasses.
- Metrics: `tests/test_sandbox_security.py` cases 299 -> 301 (+2). Validation gates this iteration: `301 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 90): expanded descriptor-rebound bound-`__getattribute__` regressions to coroutine frame pivots, adding hostile keyword-key (`**{key: ...}`) coverage for blocked `f_builtins` via a stateful `str` subclass key.
- Metrics: `tests/test_sandbox_security.py` cases 301 -> 302 (+1). Validation gates this iteration: `302 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 91): expanded descriptor-rebound bound-`__getattribute__` regressions to hostile positional-name dispatch, adding stateful `str`-subclass probes for blocked `f_locals` across traceback, coroutine, async-generator, and generator frame pivots.
- Metrics: `tests/test_sandbox_security.py` cases 302 -> 306 (+4). Validation gates this iteration: `306 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 92): expanded descriptor-rebound bound-`__getattribute__` regressions to hostile positional-name dispatch for blocked `f_builtins`, adding stateful `str`-subclass probes across traceback, coroutine, async-generator, and generator frame pivots.
- Metrics: `tests/test_sandbox_security.py` cases 306 -> 310 (+4). Validation gates this iteration: `310 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 93): expanded descriptor-rebound bound-`__getattribute__` regressions to hostile positional-name dispatch for blocked `f_globals`, adding stateful `str`-subclass probes across traceback, coroutine, async-generator, and generator frame pivots.
- Metrics: `tests/test_sandbox_security.py` cases 310 -> 314 (+4). Validation gates this iteration: `314 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).
- Progress (2026-02-28, iteration 94): expanded descriptor-rebound bound-`__getattribute__` regressions to hostile positional-name dispatch with `str.__str__`-override subclasses for blocked `f_locals` across traceback, coroutine, async-generator, and generator frame pivots.
- Metrics: `tests/test_sandbox_security.py` cases 314 -> 318 (+4). Validation gates this iteration: `318 passed` (sandbox security), `4 passed` (env strict), `15 passed` with `131 deselected` (core semantics filtered gate).

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
