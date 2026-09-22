"""Permission preparation must preserve deny precedence and directory boundaries."""
from __future__ import annotations

import argparse
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
        self.temp = tempfile.TemporaryDirectory(prefix="mathmodel-acl-test-")
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "workspaces"
        self.root.mkdir()
        self.security = prep.WindowsSecurity()
        self.sid = self.security.current_user_sid()
        self.security.set_dacl(self.root, f"O:{self.sid}D:P(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FA;;;SY)")
        self.project = self.root / "old-project"
        self.project.mkdir()
        self.deep = self.project / "deep"
        self.deep.mkdir()
        self.data = self.deep / "input.txt"
        self.data.write_text("fixture", encoding="utf-8")
        self.backup = self.base / "before.json"

    def tearDown(self):
        self.temp.cleanup()

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
