#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CPYTHON_IMPL_PATTERNS = (
    r"\bcpython_only\b",
    r"_testcapi\b",
    r"_testinternalcapi\b",
    r"_testlimitedcapi\b",
    r"_testclinic\b",
    r"_xxsubinterpreters\b",
    r"\bgettotalrefcount\b",
    r"\bCPython\b",
    r"\bcheck_impl_detail\b",
    r"\bPYTHONTHREADDEBUG\b",
)

DEFAULT_UNSUPPORTED_PATTERNS = (
    r"\b__import__\b",
    r"\b__dict__\b",
    r"\b__code__\b",
)

RESULT_MARKER = "__PYNTERP_PROBE_JSON__"
BLOCKED_ATTRIBUTE_ERROR_PREFIX = "AttributeError: attribute access to '"
BLOCKED_ATTRIBUTE_ERROR_SUFFIX = "' is blocked in this environment"
# Keep this list aligned with `pynterp.lib.guards._BLOCKED_ATTR_NAMES` so probe
# accounting consistently treats sandbox-policy blocked attrs as unsupported.
POLICY_BLOCKED_ATTR_NAMES = (
    "__base__",
    "__builtins__",
    "__closure__",
    "__code__",
    "__dict__",
    "__getattr__",
    "__getattribute__",
    "__globals__",
    "__import__",
    "__mro__",
    "__reduce__",
    "__reduce_ex__",
    "__self__",
    "__setattr__",
    "__delattr__",
    "__subclasses__",
    "f_builtins",
    "f_globals",
    "f_locals",
    "gi_frame",
)

# Some CPython test modules are predictably slower under interpretation and
# routinely exceed the global default timeout despite completing successfully.
# Keep per-file overrides narrow so probe timeout counts reflect real hangs.
SLOW_TEST_TIMEOUT_OVERRIDES: dict[str, int] = {
    "Lib/test/test_asyncio/test_events.py": 25,
    "Lib/test/test_asyncio/test_taskgroups.py": 25,
    "Lib/test/test_concurrent_futures/test_as_completed.py": 25,
    "Lib/test/test_concurrent_futures/test_process_pool.py": 40,
    "Lib/test/test_concurrent_futures/test_shutdown.py": 25,
    "Lib/test/test_concurrent_futures/test_thread_pool.py": 25,
    "Lib/test/test_free_threading/test_monitoring.py": 40,
    "Lib/test/test_queue.py": 25,
    "Lib/test/test_isinstance.py": 40,
    "Lib/test/test_zipfile64.py": 90,
}

# Explicit path-based exclusions for modules that consistently deadlock under
# in-process execution and are outside current process-sandbox compatibility.
OUT_OF_SCOPE_TEST_PATH_REASONS: dict[str, str] = {
    "test/test_concurrent_futures/test_deadlock.py": "out_of_scope:path:process_sandbox_deadlock",
}


def load_runtime_policy_blocked_attrs() -> tuple[str, ...]:
    try:
        from pynterp.lib.guards import _BLOCKED_ATTR_NAMES as runtime_blocked_attrs
    except Exception:
        return ()
    return tuple(sorted(name for name in runtime_blocked_attrs if isinstance(name, str)))


RUNNER = rf"""
from pathlib import Path
import builtins
import importlib.util
import io
import json
import os
import shutil
import sys
import types
import unittest

lib_root = Path(sys.argv[1])
test_path = Path(sys.argv[2])
pynterp_src = Path(sys.argv[3])
mode = sys.argv[4]
basis = sys.argv[5]
modname = sys.argv[6]
package = sys.argv[7]
blocked_attr_json = sys.argv[8]
try:
    blocked_attr_names = set(json.loads(blocked_attr_json))
except Exception:
    blocked_attr_names = set()

sys.path.insert(0, str(pynterp_src))
sys.path.insert(0, str(lib_root))

def patch_sys_path_probe():
    # Probe workers should execute against the injected CPython Lib tree.
    # Drop the host stdlib path so stdlib-scanning tests don't see duplicate
    # stdlib roots (which can cause collisions on copied package dirs).
    try:
        import sysconfig
    except Exception:
        return

    stdlib_path = sysconfig.get_path("stdlib")
    if not stdlib_path:
        return

    try:
        host_stdlib = Path(stdlib_path).resolve()
        probe_lib_root = Path(lib_root).resolve()
    except Exception:
        return

    if not (probe_lib_root / "os.py").is_file():
        return
    has_sysconfig = (probe_lib_root / "sysconfig.py").is_file() or (
        probe_lib_root / "sysconfig" / "__init__.py"
    ).is_file()
    if not has_sysconfig:
        return

    if host_stdlib == probe_lib_root:
        return

    filtered = []
    seen = set()
    for entry in sys.path:
        entry_text = entry if isinstance(entry, str) else str(entry)
        try:
            resolved = Path(entry_text).resolve()
        except Exception:
            resolved = None

        if resolved is not None and resolved == host_stdlib:
            continue

        key = str(resolved) if resolved is not None else entry_text
        if key in seen:
            continue
        seen.add(key)
        filtered.append(entry_text)

    sys.path[:] = filtered

patch_sys_path_probe()

from pynterp import Interpreter

def emit(payload):
    print("{RESULT_MARKER}" + json.dumps(payload))

def patch_temp_cwd_probe():
    # Avoid cross-worker races in shared cwd by remapping temp_cwd()'s
    # default "tempcwd" directory to a process-unique name.
    worker_tempcwd = f"tempcwd-{{os.getpid()}}"
    stale = Path.cwd() / worker_tempcwd
    try:
        if stale.is_symlink() or stale.is_file():
            stale.unlink()
        elif stale.is_dir():
            shutil.rmtree(stale)
    except OSError:
        pass

    try:
        from test.support import os_helper
    except Exception:
        return

    original_temp_cwd = os_helper.temp_cwd

    def wrapped_temp_cwd(name="tempcwd", quiet=False):
        if name == "tempcwd":
            name = worker_tempcwd
        return original_temp_cwd(name=name, quiet=quiet)

    os_helper.temp_cwd = wrapped_temp_cwd

patch_temp_cwd_probe()

def patch_system_limit_probe():
    # Some sandboxed environments raise PermissionError for sysconf sem-limit
    # queries. Treat that as "system-limited" for probe stability.
    try:
        import concurrent.futures.process as process_mod
    except Exception:
        return

    original = process_mod._check_system_limits

    def wrapped():
        try:
            return original()
        except PermissionError as exc:
            raise NotImplementedError(str(exc))

    process_mod._check_system_limits = wrapped

patch_system_limit_probe()

def patch_traceback_print_exc_probe():
    # CPython test trees may pass traceback.print_exc(colorize=...),
    # while the worker runtime might not support that keyword yet.
    try:
        import inspect
        import traceback
    except Exception:
        return

    original_print_exc = traceback.print_exc
    try:
        params = inspect.signature(original_print_exc).parameters
    except Exception:
        return
    if "colorize" in params:
        return

    def wrapped_print_exc(*args, **kwargs):
        kwargs.pop("colorize", None)
        return original_print_exc(*args, **kwargs)

    traceback.print_exc = wrapped_print_exc

patch_traceback_print_exc_probe()

source = test_path.read_text(encoding="utf-8", errors="ignore")
interp = Interpreter(allowed_imports=None, allow_relative_imports=True)
if mode == "module":
    name = modname
    pkg = package
else:
    name = "__main__"
    pkg = None

spec = None
loader = None
cached = None
if mode == "module":
    try:
        spec = importlib.util.spec_from_file_location(name, str(test_path))
    except Exception:
        spec = None
    if spec is not None:
        loader = getattr(spec, "loader", None)
        cached = getattr(spec, "cached", None)

env = {{
    "__name__": name,
    "__package__": pkg,
    "__file__": str(test_path),
    "__spec__": spec,
    "__loader__": loader,
    "__cached__": cached,
    "__builtins__": builtins,
}}

try:
    interp.run(source, env=env, filename=str(test_path))
except BaseException as exc:
    is_skip = isinstance(exc, unittest.SkipTest) or exc.__class__.__name__.endswith("SkipTest")
    emit(
        {{
            "status": "skip_import" if is_skip else "import_error",
            "reason": f"{{type(exc).__name__}}: {{exc}}",
        }}
    )
    raise SystemExit(0)

if basis == "files":
    emit({{"status": "ok"}})
    raise SystemExit(0)

module = types.ModuleType(name)
module.__dict__.update(env)

original_module = sys.modules.get(name)
sys.modules[name] = module
try:
    try:
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    except BaseException as exc:
        is_skip = isinstance(exc, unittest.SkipTest) or exc.__class__.__name__.endswith("SkipTest")
        emit(
            {{
                "status": "skip_suite" if is_skip else "suite_error",
                "reason": f"{{type(exc).__name__}}: {{exc}}",
            }}
        )
        raise SystemExit(0)
finally:
    if original_module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original_module


def extract_error_signature(err_text):
    for line in reversed(err_text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return "UnknownError"


def extract_blocked_attribute(signature):
    prefix = "{BLOCKED_ATTRIBUTE_ERROR_PREFIX}"
    suffix = "{BLOCKED_ATTRIBUTE_ERROR_SUFFIX}"
    if signature.startswith(prefix) and signature.endswith(suffix):
        return signature[len(prefix) : -len(suffix)]
    return None


error_signature_counts = {{}}
policy_blocked_errors = 0
for _test, err_text in result.errors:
    signature = extract_error_signature(err_text)
    error_signature_counts[signature] = error_signature_counts.get(signature, 0) + 1
    blocked_attr = extract_blocked_attribute(signature)
    if blocked_attr is not None and blocked_attr in blocked_attr_names:
        policy_blocked_errors += 1

emit(
    {{
        "status": "suite",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "policy_blocked_errors": policy_blocked_errors,
        "error_signatures": sorted(
            error_signature_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10],
    }}
)
"""


@dataclass(frozen=True)
class TestCase:
    path: Path
    module_name: str
    package_name: str
    declared_tests: int


@dataclass(frozen=True)
class ExcludedCase:
    path: Path
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe CPython tests by executing them with pynterp.",
    )
    parser.add_argument(
        "--cpython-root",
        required=True,
        type=Path,
        help="Path to CPython source tree (must contain Lib/test).",
    )
    parser.add_argument(
        "--python-exe",
        type=Path,
        help="Python executable used for worker subprocesses. Defaults to <cpython-root>/python.exe.",
    )
    parser.add_argument(
        "--pynterp-src",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src",
        help="Path that contains the pynterp package.",
    )
    parser.add_argument(
        "--mode",
        choices=("module", "script"),
        default="module",
        help="module: load test modules as packages; script: execute as __main__.",
    )
    parser.add_argument(
        "--basis",
        choices=("files", "tests"),
        default="files",
        help="files: classify at file granularity; tests: aggregate discovered unittest cases.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker subprocesses.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Per-test-file timeout in seconds.",
    )
    parser.add_argument(
        "--unsupported-pattern",
        action="append",
        default=[],
        help=(
            "Regex pattern for test source to treat as not-supported. "
            "Can be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--no-default-unsupported",
        action="store_true",
        help="Disable default unsupported filters (__import__, __dict__, __code__).",
    )
    parser.add_argument(
        "--top-files-per-category",
        type=int,
        default=10,
        help="How many example failing files to include per fail category.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional file path to write a JSON report.",
    )
    return parser.parse_args()


def discover_test_files(cpython_root: Path) -> list[Path]:
    test_root = cpython_root / "Lib" / "test"
    return sorted(path for path in test_root.rglob("*.py") if path.name.startswith("test_"))


def compile_source_patterns(raw_patterns: tuple[str, ...] | list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in raw_patterns)


def count_declared_tests(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            count += 1
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith(
                    "test_"
                ):
                    count += 1
    return count


def classify_applicability(
    test_files: list[Path],
    test_root: Path,
    *,
    impl_detail_patterns: tuple[re.Pattern[str], ...],
    unsupported_patterns: tuple[re.Pattern[str], ...],
) -> tuple[list[TestCase], list[ExcludedCase]]:
    applicable: list[TestCase] = []
    excluded: list[ExcludedCase] = []
    lib_root = test_root.parent

    for path in test_files:
        rel = path.relative_to(test_root)
        if "test_capi" in rel.parts:
            excluded.append(ExcludedCase(path=path, reason="impl_detail:path:test_capi"))
            continue

        rel_to_lib = path.relative_to(lib_root).as_posix()
        out_of_scope_reason = OUT_OF_SCOPE_TEST_PATH_REASONS.get(rel_to_lib)
        if out_of_scope_reason is not None:
            excluded.append(ExcludedCase(path=path, reason=out_of_scope_reason))
            continue

        source = path.read_text(encoding="utf-8", errors="ignore")
        impl_hit = next((p.pattern for p in impl_detail_patterns if p.search(source)), None)
        if impl_hit is not None:
            excluded.append(ExcludedCase(path=path, reason=f"impl_detail:source:{impl_hit}"))
            continue

        unsupported_hit = next((p.pattern for p in unsupported_patterns if p.search(source)), None)
        if unsupported_hit is not None:
            excluded.append(ExcludedCase(path=path, reason=f"unsupported:source:{unsupported_hit}"))
            continue

        module_name = ".".join(path.relative_to(lib_root).with_suffix("").parts)
        package_name = module_name.rpartition(".")[0]
        declared_tests = count_declared_tests(source)
        applicable.append(
            TestCase(
                path=path,
                module_name=module_name,
                package_name=package_name,
                declared_tests=declared_tests,
            )
        )

    return applicable, excluded


def categorize_failure(reason: str) -> str:
    if reason == "TIMEOUT":
        return "TIMEOUT"

    if "NotImplementedError: Statement not supported:" in reason:
        return "NotImplemented/Statement/" + reason.rsplit(":", 1)[-1].strip()
    if "NotImplementedError: Expression not supported:" in reason:
        return "NotImplemented/Expression/" + reason.rsplit(":", 1)[-1].strip()
    if "attribute access to '" in reason and "' is blocked in this environment" in reason:
        blocked = reason.split("attribute access to '", 1)[1].split("'", 1)[0]
        return f"SandboxBlockedAttribute/{blocked}"
    if reason.startswith("ImportError: from-import without module not supported"):
        return "Import/FromImportWithoutModule"
    if reason.startswith("ImportError: attempted relative import with no known parent package"):
        return "Import/RelativeImportNoPackage"
    if reason.startswith("ModuleNotFoundError: No module named "):
        missing = reason.split("No module named ", 1)[1]
        return f"ModuleNotFound/{missing}"

    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", reason)
    if match:
        return match.group(1)
    return "Unknown"


def parse_runner_payload(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    for line in reversed((proc.stdout or "").splitlines()):
        marker_at = line.find(RESULT_MARKER)
        if marker_at >= 0:
            payload = line[marker_at + len(RESULT_MARKER) :]
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                break

    output = (proc.stderr or proc.stdout or "").strip()
    reason = output.splitlines()[-1] if output else "FAILED"
    if "SkipTest" in output:
        return {"status": "skip_import", "reason": reason}
    return {"status": "import_error", "reason": reason}


def parse_error_signatures(raw_signatures: Any) -> list[tuple[str, int]]:
    if not isinstance(raw_signatures, list):
        return []

    pairs: list[tuple[str, int]] = []
    for item in raw_signatures:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue

        signature, count = item
        signature_text = str(signature).strip()
        if not signature_text:
            continue
        try:
            count_value = int(count)
        except (TypeError, ValueError):
            continue
        if count_value <= 0:
            continue

        pairs.append((signature_text, count_value))

    return pairs


def extract_blocked_attribute(reason: str) -> str | None:
    if reason.startswith(BLOCKED_ATTRIBUTE_ERROR_PREFIX) and reason.endswith(BLOCKED_ATTRIBUTE_ERROR_SUFFIX):
        return reason[len(BLOCKED_ATTRIBUTE_ERROR_PREFIX) : -len(BLOCKED_ATTRIBUTE_ERROR_SUFFIX)]
    return None


def collect_policy_blocked_attrs(raw_patterns: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    attrs: set[str] = set(POLICY_BLOCKED_ATTR_NAMES)
    attrs.update(load_runtime_policy_blocked_attrs())
    for pattern in raw_patterns:
        attrs.update(re.findall(r"__\w+__", pattern))
    return tuple(sorted(attrs))


def split_policy_blocked_suite_errors(
    *,
    total_errors: int,
    signature_pairs: list[tuple[str, int]],
    policy_blocked_attrs: set[str],
    reported_policy_blocked_errors: Any,
) -> tuple[int, int, list[tuple[str, int]]]:
    total = max(0, int(total_errors))
    filtered_signatures: list[tuple[str, int]] = []
    inferred_policy_blocked = 0

    for signature, count in signature_pairs:
        blocked_attr = extract_blocked_attribute(signature)
        if blocked_attr is not None and blocked_attr in policy_blocked_attrs:
            inferred_policy_blocked += count
            continue
        filtered_signatures.append((signature, count))

    reported = 0
    try:
        reported = int(reported_policy_blocked_errors)
    except (TypeError, ValueError):
        reported = 0
    if reported < 0:
        reported = 0

    policy_blocked = max(inferred_policy_blocked, reported)
    if policy_blocked > total:
        policy_blocked = total

    supported_errors = total - policy_blocked
    return supported_errors, policy_blocked, filtered_signatures


def run_case(
    case: TestCase,
    *,
    cpython_root: Path,
    python_exe: Path,
    pynterp_src: Path,
    mode: str,
    basis: str,
    timeout: int,
    blocked_attrs: tuple[str, ...] = (),
) -> dict[str, Any]:
    lib_root = cpython_root / "Lib"
    effective_timeout = resolve_case_timeout(
        case_path=case.path,
        cpython_root=cpython_root,
        default_timeout=timeout,
    )
    cmd = [
        str(python_exe),
        "-c",
        RUNNER,
        str(lib_root),
        str(case.path),
        str(pynterp_src),
        mode,
        basis,
        case.module_name,
        case.package_name,
        json.dumps(sorted(set(blocked_attrs))),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cpython_root),
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "reason": "TIMEOUT"}

    return parse_runner_payload(proc)


def resolve_case_timeout(*, case_path: Path, cpython_root: Path, default_timeout: int) -> int:
    timeout = max(1, int(default_timeout))
    try:
        rel_path = case_path.relative_to(cpython_root).as_posix()
    except ValueError:
        rel_path = case_path.as_posix()

    override = SLOW_TEST_TIMEOUT_OVERRIDES.get(rel_path)
    if override is not None:
        timeout = max(timeout, int(override))

    return timeout


def add_category(
    *,
    category_counts: Counter[str],
    category_files: dict[str, list[str]],
    category: str,
    case_path: str,
    weight: int,
) -> None:
    if weight <= 0:
        return
    category_counts[category] += weight
    category_files[category].append(case_path)


def main() -> int:
    args = parse_args()
    cpython_root = args.cpython_root.resolve()
    test_root = cpython_root / "Lib" / "test"
    if not test_root.exists():
        raise SystemExit(f"Missing test root: {test_root}")

    python_exe = args.python_exe.resolve() if args.python_exe else (cpython_root / "python.exe")
    if not python_exe.exists():
        raise SystemExit(f"Worker python executable not found: {python_exe}")

    pynterp_src = args.pynterp_src.resolve()
    if not pynterp_src.exists():
        raise SystemExit(f"pynterp src path not found: {pynterp_src}")

    unsupported_raw_patterns = []
    if not args.no_default_unsupported:
        unsupported_raw_patterns.extend(DEFAULT_UNSUPPORTED_PATTERNS)
    unsupported_raw_patterns.extend(args.unsupported_pattern)

    impl_detail_patterns = compile_source_patterns(CPYTHON_IMPL_PATTERNS)
    unsupported_patterns = compile_source_patterns(unsupported_raw_patterns)
    policy_blocked_attrs = collect_policy_blocked_attrs(unsupported_raw_patterns)

    all_tests = discover_test_files(cpython_root)
    applicable, excluded = classify_applicability(
        all_tests,
        test_root,
        impl_detail_patterns=impl_detail_patterns,
        unsupported_patterns=unsupported_patterns,
    )

    file_status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    category_files: dict[str, list[str]] = defaultdict(list)
    suite_error_signature_counts: Counter[str] = Counter()
    suite_error_signature_files: dict[str, list[str]] = defaultdict(list)
    failed_cases: list[str] = []

    individual_counts: Counter[str] = Counter()
    individual_counts["declared"] = sum(case.declared_tests for case in applicable)
    individual_counts["files_with_declared"] = sum(1 for case in applicable if case.declared_tests > 0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                run_case,
                case,
                cpython_root=cpython_root,
                python_exe=python_exe,
                pynterp_src=pynterp_src,
                mode=args.mode,
                basis=args.basis,
                timeout=args.timeout,
                blocked_attrs=policy_blocked_attrs,
            ): case
            for case in applicable
        }
        for future in concurrent.futures.as_completed(futures):
            case = futures[future]
            payload = future.result()
            status = str(payload.get("status", "import_error"))
            reason = str(payload.get("reason", "FAILED"))
            case_path = case.path.relative_to(cpython_root).as_posix()

            # File-level status summary.
            if status in {"ok", "suite"}:
                file_status_counts["pass"] += 1
            elif status in {"skip_import", "skip_suite"}:
                file_status_counts["skip"] += 1
            elif status == "timeout":
                file_status_counts["timeout"] += 1
            else:
                file_status_counts["fail"] += 1

            if args.basis == "files":
                if status in {"import_error", "suite_error", "timeout"}:
                    reason_counts[reason] += 1
                    category = categorize_failure(reason)
                    add_category(
                        category_counts=category_counts,
                        category_files=category_files,
                        category=category,
                        case_path=case_path,
                        weight=1,
                    )
                    failed_cases.append(case_path)
                continue

            # Individual test basis.
            if status == "suite":
                tests_run = int(payload.get("tests_run", 0))
                failures = int(payload.get("failures", 0))
                errors = int(payload.get("errors", 0))
                skipped = int(payload.get("skipped", 0))
                expected_failures = int(payload.get("expected_failures", 0))
                unexpected_successes = int(payload.get("unexpected_successes", 0))
                signature_pairs = parse_error_signatures(payload.get("error_signatures"))
                supported_errors, policy_blocked_suite_errors, signature_pairs = (
                    split_policy_blocked_suite_errors(
                        total_errors=errors,
                        signature_pairs=signature_pairs,
                        policy_blocked_attrs=set(policy_blocked_attrs),
                        reported_policy_blocked_errors=payload.get("policy_blocked_errors"),
                    )
                )

                fail_tests = failures + supported_errors + unexpected_successes
                skip_tests = skipped + expected_failures + policy_blocked_suite_errors
                pass_tests = tests_run - fail_tests - skip_tests
                if pass_tests < 0:
                    pass_tests = 0

                individual_counts["run"] += tests_run
                individual_counts["pass"] += pass_tests
                individual_counts["fail"] += fail_tests
                individual_counts["skip"] += skip_tests
                individual_counts["discovered"] += tests_run
                individual_counts["blocked_skip"] += policy_blocked_suite_errors
                individual_counts["policy_blocked_suite_error"] += policy_blocked_suite_errors

                if failures:
                    add_category(
                        category_counts=category_counts,
                        category_files=category_files,
                        category="Suite/Failure",
                        case_path=case_path,
                        weight=failures,
                    )
                if supported_errors:
                    add_category(
                        category_counts=category_counts,
                        category_files=category_files,
                        category="Suite/Error",
                        case_path=case_path,
                        weight=supported_errors,
                    )
                    if signature_pairs:
                        for signature, count in signature_pairs:
                            suite_error_signature_counts[signature] += count
                            suite_error_signature_files[signature].append(case_path)
                    else:
                        suite_error_signature_counts["UnknownErrorSignature"] += supported_errors
                        suite_error_signature_files["UnknownErrorSignature"].append(case_path)
                if unexpected_successes:
                    add_category(
                        category_counts=category_counts,
                        category_files=category_files,
                        category="Suite/UnexpectedSuccess",
                        case_path=case_path,
                        weight=unexpected_successes,
                    )
                if fail_tests:
                    failed_cases.append(case_path)
                continue

            blocked = case.declared_tests
            if blocked <= 0:
                blocked = 0

            if status in {"skip_import", "skip_suite"}:
                individual_counts["skip"] += blocked
                individual_counts["blocked_skip"] += blocked
            else:
                individual_counts["fail"] += blocked
                individual_counts["blocked_fail"] += blocked
                reason_counts[reason] += max(1, blocked)
                category = categorize_failure(reason)
                add_category(
                    category_counts=category_counts,
                    category_files=category_files,
                    category=category,
                    case_path=case_path,
                    weight=max(1, blocked),
                )
                failed_cases.append(case_path)

    applicable_count = len(applicable)
    total_count = len(all_tests)
    excluded_counts = Counter(case.reason for case in excluded)

    top_fail_categories = []
    for category, count in category_counts.most_common(20):
        top_fail_categories.append(
            {
                "category": category,
                "count": count,
                "top_files": category_files[category][: max(1, args.top_files_per_category)],
            }
        )

    top_suite_error_signatures = []
    for signature, count in suite_error_signature_counts.most_common(20):
        top_suite_error_signatures.append(
            {
                "signature": signature,
                "count": count,
                "top_files": suite_error_signature_files[signature][: max(1, args.top_files_per_category)],
            }
        )

    report: dict[str, Any] = {
        "basis": args.basis,
        "mode": args.mode,
        "cpython_root": str(cpython_root),
        "python_exe": str(python_exe),
        "pynterp_src": str(pynterp_src),
        "unsupported_patterns": list(unsupported_raw_patterns),
        "total_test_files": total_count,
        "applicable_test_files": applicable_count,
        "not_applicable_test_files": len(excluded),
        "not_applicable_breakdown": excluded_counts.most_common(30),
        "file_status_counts": {
            "pass": file_status_counts["pass"],
            "skip": file_status_counts["skip"],
            "fail": file_status_counts["fail"],
            "timeout": file_status_counts["timeout"],
        },
        "file_percentages": {
            "applicable_of_total": (applicable_count / total_count * 100.0) if total_count else 0.0,
            "pass_of_applicable": (
                (file_status_counts["pass"] / applicable_count * 100.0) if applicable_count else 0.0
            ),
            "pass_plus_skip_of_applicable": (
                ((file_status_counts["pass"] + file_status_counts["skip"]) / applicable_count * 100.0)
                if applicable_count
                else 0.0
            ),
        },
        "top_fail_reasons": reason_counts.most_common(20),
        "top_fail_categories": top_fail_categories,
        "top_suite_error_signatures": top_suite_error_signatures,
        "sample_failed_cases": failed_cases[:50],
    }

    if args.basis == "tests":
        individual_total = individual_counts["pass"] + individual_counts["fail"] + individual_counts["skip"]
        report["individual_test_counts"] = {
            "declared": individual_counts["declared"],
            "files_with_declared": individual_counts["files_with_declared"],
            "discovered_and_run": individual_counts["run"],
            "pass": individual_counts["pass"],
            "fail": individual_counts["fail"],
            "skip": individual_counts["skip"],
            "blocked_fail": individual_counts["blocked_fail"],
            "blocked_skip": individual_counts["blocked_skip"],
            "policy_blocked_suite_error": individual_counts["policy_blocked_suite_error"],
            "estimated_total": individual_total,
        }
        report["individual_percentages"] = {
            "pass_of_estimated_total": (
                (individual_counts["pass"] / individual_total * 100.0) if individual_total else 0.0
            ),
            "pass_plus_skip_of_estimated_total": (
                ((individual_counts["pass"] + individual_counts["skip"]) / individual_total * 100.0)
                if individual_total
                else 0.0
            ),
        }

    print(f"basis: {args.basis}")
    print(f"mode: {args.mode}")
    print(f"total_test_files: {total_count}")
    print(f"applicable_test_files: {applicable_count}")
    print(f"not_applicable_test_files: {len(excluded)}")
    print(f"file_pass: {file_status_counts['pass']}")
    print(f"file_skip: {file_status_counts['skip']}")
    print(f"file_fail: {file_status_counts['fail']}")
    print(f"file_timeout: {file_status_counts['timeout']}")
    print(f"applicable_of_total_file_pct: {report['file_percentages']['applicable_of_total']:.2f}")
    print(f"pass_of_applicable_file_pct: {report['file_percentages']['pass_of_applicable']:.2f}")
    print(
        "pass_plus_skip_of_applicable_file_pct: "
        f"{report['file_percentages']['pass_plus_skip_of_applicable']:.2f}"
    )

    if args.basis == "tests":
        it = report["individual_test_counts"]
        ip = report["individual_percentages"]
        print(f"declared_individual_tests: {it['declared']}")
        print(f"discovered_and_run_individual_tests: {it['discovered_and_run']}")
        print(f"estimated_individual_tests_total: {it['estimated_total']}")
        print(f"individual_pass: {it['pass']}")
        print(f"individual_skip: {it['skip']}")
        print(f"individual_fail: {it['fail']}")
        print(f"individual_blocked_fail: {it['blocked_fail']}")
        print(f"individual_blocked_skip: {it['blocked_skip']}")
        print(f"individual_policy_blocked_suite_error: {it['policy_blocked_suite_error']}")
        print(f"pass_of_estimated_individual_pct: {ip['pass_of_estimated_total']:.2f}")
        print(
            "pass_plus_skip_of_estimated_individual_pct: "
            f"{ip['pass_plus_skip_of_estimated_total']:.2f}"
        )

    print("top_fail_reasons:")
    for reason, count in report["top_fail_reasons"]:
        print(f"{count:4d} | {reason}")

    print("top_fail_categories:")
    for item in top_fail_categories:
        print(f"{item['count']:4d} | {item['category']}")
        for path in item["top_files"]:
            print(f"       - {path}")

    if top_suite_error_signatures:
        print("top_suite_error_signatures:")
        for item in top_suite_error_signatures:
            print(f"{item['count']:4d} | {item['signature']}")
            for path in item["top_files"]:
                print(f"       - {path}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"json_report: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
