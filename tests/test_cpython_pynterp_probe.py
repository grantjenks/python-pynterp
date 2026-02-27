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


def test_run_case_cleans_stale_tempcwd(tmp_path: Path) -> None:
    probe = load_probe_module()
    cpython_root = tmp_path / "cpython"
    lib_root = cpython_root / "Lib"
    test_root = lib_root / "test"
    test_root.mkdir(parents=True)
    (cpython_root / "tempcwd").mkdir()

    test_path = test_root / "test_stale_tempcwd.py"
    test_path.write_text(
        """
import os
import shutil
import unittest

def setUpModule():
    os.mkdir("tempcwd")

def tearDownModule():
    shutil.rmtree("tempcwd", ignore_errors=True)

class TempCwdCase(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
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
