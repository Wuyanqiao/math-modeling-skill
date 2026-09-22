import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_distribution as distribution
import sync_dsh_plugin as synchronize


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="分发测试 with spaces ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "source"
        self.root.mkdir()
        policy = distribution.read_policy(ROOT)
        policy["skill_paths"] = ["SKILL.md", "VERSION", "pyproject.toml", "scripts", "tools", "mathmodel_runtime", "distribution-policy.json", "project-review"]
        policy["required_resources"] = ["SKILL.md", "VERSION", "scripts/mathmodel.py", "mathmodel_runtime/__init__.py"]
        policy["local_only_required_resources"] = ["tools/docx/scripts/check_env.py"]
        self.policy = policy
        self.write("distribution-policy.json", json.dumps(policy))
        self.write("SKILL.md", "[Helper](tools/docx/scripts/check_env.py)\n")
        self.write("VERSION", "2.0.0\n")
        self.write("pyproject.toml", '[project]\nrequires-python = ">=3.11,<3.14"\ndependencies=[]\n')
        self.write("scripts/mathmodel.py", "import json\nprint(json.dumps({'ok': True, 'done': False}))\n")
        self.write("tools/docx/scripts/check_env.py", "print('doctor')\n")
        self.write("mathmodel_runtime/__init__.py", "")
        self.write("dsh-plugin/math-modeling-agent/plugins/main.js", "export const active = true;\n")
        self.output = self.root.parent / "archives"

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_release_fails_closed_before_writing_archives(self):
        with self.assertRaisesRegex(distribution.DistributionError, "authorization is unverified"):
            distribution.build(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_restricted_components_are_excluded_even_when_other_files_allowed(self):
        files = {"tools/docx/scripts/check_env.py": self.root / "tools/docx/scripts/check_env.py"}
        accepted, omitted = distribution.authorize(files, self.policy, "release")
        self.assertEqual(accepted, {})
        self.assertEqual(omitted[0]["component"], "restricted-docx")

    def test_allow_requires_license_and_an_existing_evidence_file(self):
        policy = {"components": [{"id": "test", "prefixes": ["scripts"], "release": "allow", "license": "example", "evidence": "MISSING"}]}
        with self.assertRaises(distribution.DistributionError):
            distribution.authorize({"scripts/mathmodel.py": self.root / "scripts/mathmodel.py"}, policy, "release")

    def test_unclassified_resource_blocks_release(self):
        with self.assertRaisesRegex(distribution.DistributionError, "unclassified"):
            distribution.authorize({"unknown.txt": self.write("unknown.txt", "unclassified")}, self.policy, "release")

    def test_authorization_evidence_must_stay_inside_source_tree(self):
        (self.root.parent / "external-license.txt").write_text("external file")
        policy = {"components": [{"id": "test", "prefixes": ["scripts"], "release": "allow", "license": "example", "evidence": "../external-license.txt"}]}
        with self.assertRaises(distribution.DistributionError):
            distribution.authorize({"scripts/mathmodel.py": self.root / "scripts/mathmodel.py"}, policy, "release")

    def test_local_archive_is_complete_labelled_and_ignores_checkout_mirror(self):
        self.write("project-review/.venv/secret.txt", "do not package")
        self.write("tools/__pycache__/cache.pyc", "do not package")
        self.write("dsh-plugin/math-modeling-agent/skills/math-modeling/SKILL.md", "stale mirror")
        self.write("dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/skills/math-modeling/SKILL.md", "stale npm mirror")
        report = distribution.build(self.root, self.output, "local-development")
        self.assertFalse(report["redistribution_approved"])
        self.assertEqual(len(report["artifacts"]), 2)
        archive = self.output / next(item["name"] for item in report["artifacts"] if "-dsh-" in item["name"])
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            prefix = "math-modeling-agent/skills/math-modeling/"
            self.assertIn(prefix + "tools/docx/scripts/check_env.py", names)
            self.assertEqual(bundle.read(prefix + "SKILL.md"), (self.root / "SKILL.md").read_bytes())
            npm_prefix = "math-modeling-agent/plugins/dsh-math-modeling-ui/skills/math-modeling/"
            self.assertEqual(bundle.read(npm_prefix + "SKILL.md"), (self.root / "SKILL.md").read_bytes())
            self.assertIn(npm_prefix + "tools/docx/scripts/check_env.py", names)
            self.assertIn("math-modeling-agent/" + distribution.LOCAL_NOTICE, names)
            self.assertFalse(any("project-review" in name or "__pycache__" in name for name in names))
            manifest = json.loads(bundle.read("math-modeling-agent/" + distribution.MANIFEST))
            self.assertIn("skills/math-modeling/" + distribution.MANIFEST, manifest["files"])
            self.assertEqual(manifest["components"]["skill"], "2.0.0")

    def test_resource_audit_detects_an_omitted_executable_reference(self):
        stage = self.root.parent / "stage"
        shutil.copytree(self.root, stage)
        (stage / "tools/docx/scripts/check_env.py").unlink()
        with self.assertRaisesRegex(distribution.DistributionError, "omitted_link_targets"):
            distribution.audit_resources(self.root, stage, self.policy, "local-development")

    def test_manifest_detects_modified_payload_and_extra_files(self):
        stage = self.root.parent / "stage"
        stage.mkdir()
        (stage / "payload.txt").write_text("original")
        distribution.write_manifest(stage, {"mode": "local-development"})
        distribution.verify_manifest(stage)
        (stage / "payload.txt").write_text("modified")
        with self.assertRaisesRegex(distribution.DistributionError, "hash mismatch"):
            distribution.verify_manifest(stage)
        (stage / "extra.txt").write_text("extra")
        with self.assertRaisesRegex(distribution.DistributionError, "inventory mismatch"):
            distribution.verify_manifest(stage)

    def test_check_mode_does_not_create_destination(self):
        destination = self.root / "dsh-plugin/math-modeling-agent/skills/math-modeling"
        report = synchronize.synchronize(self.root, destination)
        self.assertTrue(report["changes"])
        self.assertFalse(destination.exists())

    def test_sync_copies_scripts_removes_stale_tools_and_becomes_idempotent(self):
        destination = self.root / "dsh-plugin/math-modeling-agent/skills/math-modeling"
        stale = destination / "tools/removed/SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("obsolete")
        synchronize.synchronize(self.root, destination, apply=True)
        self.assertFalse(stale.exists())
        self.assertTrue((destination / "tools/docx/scripts/check_env.py").is_file())
        self.assertEqual(synchronize.synchronize(self.root, destination)["changes"], [])

    def test_sync_refuses_a_destination_outside_generated_directory(self):
        with self.assertRaises(distribution.DistributionError):
            synchronize.synchronize(self.root, self.root.parent / "outside", apply=True)

    def test_invalid_version_cannot_escape_output_directory(self):
        self.write("VERSION", "../../escape")
        with self.assertRaisesRegex(distribution.DistributionError, "semantic version"):
            distribution.build(self.root, self.output, "local-development")


if __name__ == "__main__":
    unittest.main()
