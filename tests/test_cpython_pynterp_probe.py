from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_probe_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "cpython_pynterp_probe.py"
    module_name = "_test_cpython_pynterp_probe"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_error_signatures_accepts_valid_entries() -> None:
    probe = load_probe_module()
    raw = [
        ["ValueError: boom", 2],
        ("TypeError: bad", "3"),
        [" ", 4],
        ["RuntimeError: fail", 0],
        ["NameError: x", "invalid"],
        ["IndexError: oob", -1],
        ["AssertionError: nope", 1],
    ]

    assert probe.parse_error_signatures(raw) == [
        ("ValueError: boom", 2),
        ("TypeError: bad", 3),
        ("AssertionError: nope", 1),
    ]


def test_parse_error_signatures_rejects_non_list_payload() -> None:
    probe = load_probe_module()
    assert probe.parse_error_signatures(None) == []
    assert probe.parse_error_signatures({"ValueError: boom": 2}) == []


def test_run_case_executes_module_fixtures(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    lib_root = cpython_root / "Lib"
    test_root = lib_root / "test"
    test_root.mkdir(parents=True)
    test_path = test_root / "test_module_fixture.py"
    test_path.write_text(
        """
import unittest

MODULE_FLAG = None

def setUpModule():
    global MODULE_FLAG
    MODULE_FLAG = object()

class ModuleFixtureCase(unittest.TestCase):
    def test_fixture_ran(self):
        self.assertIsNotNone(MODULE_FLAG)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_module_fixture",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_run_case_seeds_module_loader_for_linecache_lazycache(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    test_root = cpython_root / "Lib" / "test"
    test_root.mkdir(parents=True)
    test_path = test_root / "test_linecache_lazycache.py"
    test_path.write_text(
        """
import linecache
import unittest

NONEXISTENT = linecache.__file__ + '.missing'

class LinecacheLazycacheCase(unittest.TestCase):
    def test_lazycache_uses_module_loader(self):
        linecache.clearcache()
        try:
            self.assertTrue(linecache.lazycache(NONEXISTENT, globals()))
            self.assertEqual(1, len(linecache.cache[NONEXISTENT]))
        finally:
            linecache.clearcache()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_linecache_lazycache",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_run_case_isolates_default_tempcwd_name(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    lib_root = cpython_root / "Lib"
    test_root = lib_root / "test"
    test_root.mkdir(parents=True)
    support_root = test_root / "support"
    support_root.mkdir()
    (test_root / "__init__.py").write_text("", encoding="utf-8")
    (support_root / "__init__.py").write_text("", encoding="utf-8")
    (support_root / "os_helper.py").write_text(
        """
import contextlib
import os
import shutil

@contextlib.contextmanager
def temp_cwd(name='tempcwd', quiet=False):
    os.mkdir(name)
    saved = os.getcwd()
    os.chdir(name)
    try:
        yield os.getcwd()
    finally:
        os.chdir(saved)
        shutil.rmtree(name, ignore_errors=True)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (cpython_root / "tempcwd").mkdir()

    test_path = test_root / "test_stale_tempcwd.py"
    test_path.write_text(
        """
import os
import shutil
import unittest
from test.support.os_helper import temp_cwd

def setUpModule():
    shutil.rmtree("tempcwd", ignore_errors=True)
    os.mkdir("tempcwd")

def tearDownModule():
    shutil.rmtree("tempcwd", ignore_errors=True)

class TempCwdCase(unittest.TestCase):
    def test_ok(self):
        with temp_cwd():
            with open("messages.po", "w", encoding="utf-8") as fh:
                fh.write("msgid \\"x\\"\\nmsgstr \\"y\\"\\n")
            self.assertTrue(os.path.exists("messages.po"))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_stale_tempcwd",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_run_case_normalizes_sysconf_permission_error(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    lib_root = cpython_root / "Lib"
    test_root = lib_root / "test"
    test_root.mkdir(parents=True)

    test_path = test_root / "test_sysconf_permission.py"
    test_path.write_text(
        """
import os
import unittest

_orig_sysconf = os.sysconf

def _deny_sysconf(name):
    raise PermissionError(1, "Operation not permitted")

os.sysconf = _deny_sysconf
try:
    from concurrent.futures.process import _check_system_limits
    try:
        _check_system_limits()
        HAVE_MULTIPROCESSING = True
    except (NotImplementedError, ModuleNotFoundError):
        HAVE_MULTIPROCESSING = False
finally:
    os.sysconf = _orig_sysconf

class SysconfPermissionCase(unittest.TestCase):
    def test_permission_error_becomes_not_implemented(self):
        self.assertFalse(HAVE_MULTIPROCESSING)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_sysconf_permission",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_run_case_normalizes_traceback_print_exc_colorize_kw(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    lib_root = cpython_root / "Lib"
    test_root = lib_root / "test"
    test_root.mkdir(parents=True)

    test_path = test_root / "test_traceback_colorize_kw.py"
    test_path.write_text(
        """
import io
import traceback
import unittest

class TracebackColorizeKwCase(unittest.TestCase):
    def test_print_exc_accepts_colorize_kw(self):
        stream = io.StringIO()
        try:
            1 / 0
        except ZeroDivisionError:
            traceback.print_exc(file=stream, colorize=False)
        self.assertIn("ZeroDivisionError", stream.getvalue())
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_traceback_colorize_kw",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_run_case_uses_live_builtins_for_rebinding(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    test_root = cpython_root / "Lib" / "test"
    test_root.mkdir(parents=True)

    test_path = test_root / "test_live_builtins.py"
    test_path.write_text(
        """
import builtins
import unittest

class LiveBuiltinsCase(unittest.TestCase):
    def test_rebinding_len_updates_user_function_lookup(self):
        def foo():
            return len([1, 2, 3])

        original = builtins.len
        builtins.len = lambda _value: 7
        try:
            self.assertEqual(foo(), 7)
        finally:
            builtins.len = original
""".strip()
        + "\n",
        encoding="utf-8",
    )
    case = probe.TestCase(
        path=test_path,
        module_name="test_live_builtins",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["failures"] == 0
    assert payload["errors"] == 0


def test_default_unsupported_patterns_include_dunder_code() -> None:
    probe = load_probe_module()
    assert r"\b__code__\b" in probe.DEFAULT_UNSUPPORTED_PATTERNS


def test_resolve_case_timeout_applies_slow_module_override(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    case_path = cpython_root / "Lib" / "test" / "test_zipfile64.py"
    timeout = probe.resolve_case_timeout(
        case_path=case_path,
        cpython_root=cpython_root,
        default_timeout=10,
    )
    assert timeout == 90


def test_resolve_case_timeout_keeps_default_for_non_overridden_modules(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    case_path = cpython_root / "Lib" / "test" / "test_sched.py"
    timeout = probe.resolve_case_timeout(
        case_path=case_path,
        cpython_root=cpython_root,
        default_timeout=10,
    )
    assert timeout == 10


def test_classify_applicability_excludes_dunder_code_by_default(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    test_root = cpython_root / "Lib" / "test"
    test_root.mkdir(parents=True)
    test_path = test_root / "test_dunder_code_policy.py"
    test_path.write_text(
        """
def test_policy():
    return (lambda: None).__code__
""".strip()
        + "\n",
        encoding="utf-8",
    )

    test_files = probe.discover_test_files(cpython_root)
    applicable, excluded = probe.classify_applicability(
        test_files,
        test_root,
        impl_detail_patterns=probe.compile_source_patterns(probe.CPYTHON_IMPL_PATTERNS),
        unsupported_patterns=probe.compile_source_patterns(probe.DEFAULT_UNSUPPORTED_PATTERNS),
    )

    assert applicable == []
    assert len(excluded) == 1
    assert excluded[0].path == test_path
    assert "__code__" in excluded[0].reason


def test_collect_policy_blocked_attrs_extracts_dunder_names() -> None:
    probe = load_probe_module()
    attrs = probe.collect_policy_blocked_attrs(
        [r"\b__code__\b", r"foo|__dict__", r"\bnot_a_dunder\b", r"\b__import__\b"]
    )
    assert "__code__" in attrs
    assert "__dict__" in attrs
    assert "__import__" in attrs
    assert "__globals__" in attrs
    assert "f_globals" in attrs


def test_collect_policy_blocked_attrs_includes_runtime_guard_attrs() -> None:
    probe = load_probe_module()
    from pynterp.lib import guards

    attrs = set(probe.collect_policy_blocked_attrs([]))
    assert set(guards._BLOCKED_ATTR_NAMES).issubset(attrs)


def test_split_policy_blocked_suite_errors_filters_policy_signatures() -> None:
    probe = load_probe_module()
    signature_pairs = [
        ("AttributeError: attribute access to '__code__' is blocked in this environment", 2),
        ("RuntimeError: boom", 1),
    ]
    supported_errors, policy_blocked_errors, filtered = probe.split_policy_blocked_suite_errors(
        total_errors=4,
        signature_pairs=signature_pairs,
        policy_blocked_attrs={"__code__"},
        reported_policy_blocked_errors=1,
    )

    assert supported_errors == 2
    assert policy_blocked_errors == 2
    assert filtered == [("RuntimeError: boom", 1)]


def test_split_policy_blocked_suite_errors_filters_runtime_guard_attrs() -> None:
    probe = load_probe_module()
    signature_pairs = [
        ("AttributeError: attribute access to 'f_globals' is blocked in this environment", 2),
        ("AttributeError: attribute access to '__globals__' is blocked in this environment", 1),
        ("TypeError: boom", 1),
    ]
    supported_errors, policy_blocked_errors, filtered = probe.split_policy_blocked_suite_errors(
        total_errors=4,
        signature_pairs=signature_pairs,
        policy_blocked_attrs=set(probe.collect_policy_blocked_attrs([])),
        reported_policy_blocked_errors=0,
    )

    assert supported_errors == 1
    assert policy_blocked_errors == 3
    assert filtered == [("TypeError: boom", 1)]


def test_run_case_reports_policy_blocked_suite_errors(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    test_root = cpython_root / "Lib" / "test"
    test_root.mkdir(parents=True)
    test_path = test_root / "test_policy_blocked_suite_errors.py"
    test_path.write_text(
        """
import unittest

class PolicyBlockedCase(unittest.TestCase):
    def test_blocked(self):
        raise AttributeError("attribute access to '__code__' is blocked in this environment")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    case = probe.TestCase(
        path=test_path,
        module_name="test_policy_blocked_suite_errors",
        package_name="",
        declared_tests=1,
    )
    payload = probe.run_case(
        case,
        cpython_root=cpython_root,
        python_exe=Path(sys.executable),
        pynterp_src=Path(__file__).resolve().parents[1] / "src",
        mode="module",
        basis="tests",
        timeout=10,
        blocked_attrs=("__code__",),
    )

    assert payload["status"] == "suite"
    assert payload["tests_run"] == 1
    assert payload["errors"] == 1
    assert payload["policy_blocked_errors"] == 1
