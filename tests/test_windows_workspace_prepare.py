"""Permission preparation must preserve deny precedence and directory boundaries."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest

SPEC = importlib.util.spec_from_file_location("workspace_prepare", Path(__file__).resolve().parents[1] / "scripts" / "prepare_dsh_windows_workspace.py")
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)


def fixture_token_privileges(process_id=None, restore=None):
    """Remove ownership bypasses from this test process, saving their state."""
    from ctypes import wintypes as w
    if process_id is not None and process_id != os.getppid():
        raise ValueError("Only this fixture's direct parent process may be adjusted")

    class Luid(ctypes.Structure):
        _fields_ = [("low", w.DWORD), ("high", w.LONG)]

    class Privilege(ctypes.Structure):
        _fields_ = [("luid", Luid), ("attributes", w.DWORD)]

    class TokenPrivileges(ctypes.Structure):
        _fields_ = [("count", w.DWORD), ("privilege", Privilege)]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    api.LookupPrivilegeValueW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.POINTER(Luid)]
    api.AdjustTokenPrivileges.argtypes = [w.HANDLE, w.BOOL, ctypes.POINTER(TokenPrivileges), w.DWORD, ctypes.POINTER(TokenPrivileges), ctypes.POINTER(w.DWORD)]
    process = kernel.OpenProcess(0x1000, False, process_id) if process_id else kernel.GetCurrentProcess()
    token = w.HANDLE()
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    previous = []
    try:
        if not api.OpenProcessToken(process, 0x28, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        changes = restore if restore is not None else [{"name": name, "attributes": 0} for name in ("SeTakeOwnershipPrivilege", "SeRestorePrivilege")]
        for change in changes:
            state, old, size = TokenPrivileges(), TokenPrivileges(), w.DWORD()
            state.count = 1
            state.privilege.attributes = change["attributes"]
            if not api.LookupPrivilegeValueW(None, change["name"], ctypes.byref(state.privilege.luid)):
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.set_last_error(0)
            if not api.AdjustTokenPrivileges(token, False, ctypes.byref(state), ctypes.sizeof(old), ctypes.byref(old), ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            error = ctypes.get_last_error()
            if error not in (0, 1300):  # A standard user may not possess either privilege.
                raise ctypes.WinError(error)
            if old.count:
                previous.append({"name": change["name"], "attributes": old.privilege.attributes})
    finally:
        if token:
            kernel.CloseHandle(token)
        if process_id:
            kernel.CloseHandle(process)
    return previous


class AceTests(unittest.TestCase):
    def test_allow_preserves_explicit_deny_precedence(self):
        original = "O:SYD:AI(D;;WO;;;WD)(A;;FA;;;SY)(A;ID;FR;;;BU)S:(ML;;NW;;;LW)"
        revised = prep.insert_rule(original)
        self.assertLess(revised.index("(D;;WO;;;WD)"), revised.index(prep.CREATOR_OWNER_ACE))
        self.assertTrue(revised.endswith("S:(ML;;NW;;;LW)"))
        self.assertTrue(prep.denies_write_owner(revised))

    def test_rejects_noncanonical_or_conditional_acl(self):
        for value in ["D:(A;;FA;;;SY)(D;;WO;;;WD)", "D:(XA;;FA;;;WD;(@User.x == 1))", "D:NO_ACCESS_CONTROL"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                prep.insert_rule(value)

    def test_exact_rule_excludes_recursive_or_file_inheritance(self):
        self.assertFalse(prep.has_rule("D:(A;CIIO;WO;;;CO)"))
        self.assertFalse(prep.has_rule("D:(A;OICINPIO;WO;;;CO)"))
        self.assertTrue(prep.has_rule("D:(A;IOCINP;0x80000;;;S-1-3-0)"))

    def test_rollback_removes_only_recorded_permission(self):
        source = "O:SYD:(D;CI;DT;;;WD)" + prep.CREATOR_OWNER_ACE + "(A;OICI;0x110156;;;S-1-4-12-34)S:(ML;OICI;NW;;;LW)"
        revised, removed = prep.remove_recorded_ace(source, prep.CREATOR_OWNER_ACE)
        self.assertTrue(removed)
        self.assertIn("S-1-4-12-34", revised)
        self.assertIn("(D;CI;DT;;;WD)", revised)
        self.assertTrue(revised.endswith("S:(ML;OICI;NW;;;LW)"))

    def test_rollback_ambiguous_duplicate_refused(self):
        with self.assertRaises(ValueError):
            prep.remove_recorded_ace("D:" + prep.CREATOR_OWNER_ACE * 2, prep.CREATOR_OWNER_ACE)

    def test_all_write_owner_deny_spellings_detected(self):
        for rights in ["WO", "GA", "FA", "0x80000", "0x10000000", "0x1f01ff"]:
            with self.subTest(rights=rights):
                self.assertTrue(prep.denies_write_owner(f"D:(D;CIID;{rights};;;WD)"))
        self.assertFalse(prep.denies_write_owner("D:(D;CI;DT;;;WD)"))


@unittest.skipUnless(os.name == "nt", "Windows security descriptor integration")
class WindowsPreparationTests(unittest.TestCase):
    def setUp(self):
        privileges = fixture_token_privileges()
        self.addCleanup(lambda: fixture_token_privileges(restore=privileges))
        self.temp = tempfile.TemporaryDirectory(prefix="mathmodel-acl-test-")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup_fixture)
        self.root = self.base / "workspaces"
        self.root.mkdir()
        self.security = prep.WindowsSecurity()
        self.sid = self.security.current_user_sid()
        self.project = self.root / "old-project"
        self.project.mkdir()
        # An elevated runner can default to Administrators as the owner. Set
        # the child's owner while the fixture still has its original access.
        self.fixture_security(self.project, f"O:{self.sid}D:(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FA;;;SY)", 0x20000005)
        self.fixture_security(self.root, f"O:{self.sid}D:P(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FA;;;SY)", 0x80000005)
        for target in (self.root, self.project):
            diagnostic = self.permission_diagnostic(target)
            self.assertTrue(self.security.read(target).startswith(f"O:{self.sid}"), diagnostic)
            self.assertTrue(self.security.access(target)["WRITE_DAC"]["granted"], diagnostic)
            self.assertFalse(self.security.access(target)["WRITE_OWNER"]["granted"], diagnostic)
        self.assertIn("D:P", self.security.read(self.root), self.permission_diagnostic(self.root))
        self.deep = self.project / "deep"
        self.deep.mkdir()
        self.data = self.deep / "input.txt"
        self.data.write_text("fixture", encoding="utf-8")
        self.backup = self.base / "before.json"

    def cleanup_fixture(self):
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(self.base.name.startswith("mathmodel-acl-test-"))
        self.temp.cleanup()

    def permission_diagnostic(self, target):
        return json.dumps({"path": str(target), "sddl": self.security.read(target), "access": self.security.access(target)})

    def fixture_security(self, target, sddl, information):
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(self.base.name.startswith("mathmodel-acl-test-"))
        self.assertTrue(target.resolve().is_relative_to(self.base))
        for part in (target, *target.parents):
            self.assertFalse(prep.is_reparse(part), str(part))
            if part == self.base:
                break
        security = self.security
        sd, owner, acl = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        present, defaulted = security.w.BOOL(), security.w.BOOL()
        if not security.api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            security.api.GetSecurityDescriptorOwner.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(security.w.BOOL)]
            if not security.api.GetSecurityDescriptorOwner(sd, ctypes.byref(owner), ctypes.byref(defaulted)):
                raise ctypes.WinError(ctypes.get_last_error())
            if information & 4 and not security.api.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)):
                raise ctypes.WinError(ctypes.get_last_error())
            result = security.api.SetNamedSecurityInfoW(str(target), 1, information, owner, None, acl, None)
            if result:
                raise OSError(result, "Cannot construct isolated test ACL")
        finally:
            security.kernel.LocalFree(sd)

    def args(self, **kwargs):
        return argparse.Namespace(workspace_parent=str(self.root), apply=False, backup=None, rollback=None, **kwargs)

    def test_readonly_apply_idempotent_and_precise_rollback(self):
        before = {p: self.security.read(p) for p in [self.root, self.project, self.deep, self.data]}
        inspected = prep.prepare(self.args(), self.security)
        self.assertFalse(inspected["changed"])
        self.assertEqual(before, {p: self.security.read(p) for p in before})
        args = self.args(); args.apply = True; args.backup = str(self.backup)
        result = prep.prepare(args, self.security)
        self.assertTrue(result["changed"])
        self.assertEqual(before[self.deep], self.security.read(self.deep))
        self.assertEqual(before[self.data], self.security.read(self.data))
        self.assertFalse(self.security.access(self.root)["WRITE_OWNER"]["granted"])
        self.assertTrue(self.security.access(self.project)["WRITE_OWNER"]["granted"])
        self.assertFalse(prep.prepare(args, self.security)["changed"])
        new = self.root / "new-project"; new.mkdir()
        self.assertTrue(self.security.access(new)["WRITE_OWNER"]["granted"])
        unrelated = "(A;;FR;;;BU)"
        self.security.set_dacl(self.project, prep.insert_allow(self.security.read(self.project), unrelated))
        rollback = self.args(); rollback.rollback = str(self.backup); rollback.backup = str(self.base / "rollback-before.json")
        reverted = prep.prepare(rollback, self.security)
        self.assertTrue(reverted["changed"])
        self.assertIn(unrelated, self.security.read(self.project))
        self.assertFalse(self.security.access(self.project)["WRITE_OWNER"]["granted"])
        self.assertTrue(self.security.access(new)["WRITE_OWNER"]["granted"])
        future = self.root / "after-rollback"; future.mkdir()
        self.assertFalse(self.security.access(future)["WRITE_OWNER"]["granted"])

    def test_backup_required_before_any_change(self):
        before = self.security.read(self.root)
        args = self.args(); args.apply = True
        with self.assertRaises(ValueError):
            prep.prepare(args, self.security)
        self.assertEqual(before, self.security.read(self.root))

    def test_existing_write_owner_deny_is_not_overridden(self):
        sd = self.security.read(self.project)
        start = sd.index("(")
        denied = sd[:start] + f"(D;;WO;;;{self.sid})" + sd[start:]
        self.security.set_dacl(self.project, denied)
        before = self.security.read(self.project)
        args = self.args(); args.apply = True; args.backup = str(self.backup)
        report = prep.prepare(args, self.security)
        self.assertTrue(any("deny" in item["reason"] for item in report["skipped"]))
        self.assertEqual(before, self.security.read(self.project))
        self.assertFalse(self.security.access(self.project)["WRITE_OWNER"]["granted"])

    def test_root_and_escaping_rollback_refused(self):
        args = self.args(); args.workspace_parent = self.root.anchor
        with self.assertRaises(ValueError):
            prep.prepare(args, self.security)
        args = self.args(); args.apply = True; args.backup = str(self.backup)
        prep.prepare(args, self.security)
        document = json.loads(self.backup.read_text(encoding="utf-8"))
        document["changes"][0]["relative_path"] = "../outside"
        bad = self.base / "malformed.json"; bad.write_text(json.dumps(document), encoding="utf-8")
        args = self.args(); args.rollback = str(bad); args.backup = str(self.base / "other.json")
        before = self.security.read(self.root)
        with self.assertRaises(ValueError):
            prep.prepare(args, self.security)
        self.assertEqual(before, self.security.read(self.root))

    def test_direct_junction_refused_before_backup_or_mutation(self):
        outside = self.base / "outside"; outside.mkdir()
        junction = self.root / "junction"
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True)
        before = self.security.read(self.root)
        args = self.args(); args.apply = True; args.backup = str(self.backup)
        with self.assertRaises(ValueError):
            prep.prepare(args, self.security)
        self.assertEqual(before, self.security.read(self.root))
        self.assertFalse(self.backup.exists())

    def test_rollback_ignores_unrelated_later_junction(self):
        args = self.args(); args.apply = True; args.backup = str(self.backup)
        prep.prepare(args, self.security)
        outside = self.base / "outside"; outside.mkdir()
        junction = self.root / "later-junction"
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True)
        outside_before = self.security.read(outside)
        rollback = self.args(); rollback.rollback = str(self.backup); rollback.backup = str(self.base / "rollback-before.json")
        report = prep.prepare(rollback, self.security)
        self.assertTrue(report["changed"])
        self.assertFalse(self.security.access(self.project)["WRITE_OWNER"]["granted"])
        self.assertEqual(outside_before, self.security.read(outside))


if __name__ == "__main__":
    unittest.main()
