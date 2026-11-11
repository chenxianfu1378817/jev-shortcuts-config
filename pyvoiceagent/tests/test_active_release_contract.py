"""Offline contract for the *active* PYVoiceAgent release, not an old pinned build.

Never imports or executes the production engine. Safe without Pythonista/iOS.
"""
from __future__ import annotations
import ast
import hashlib
import hmac
import json
from pathlib import Path
import re
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
LEGACY_LIMIT = 350_000
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("manifest has a duplicate key: " + key)
        result[key] = value
    return result


def validate_active_release(directory: Path) -> dict:
    """Fail closed for bad manifest, version, byte length, digest or syntax."""
    directory = Path(directory)
    try:
        manifest = json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest cannot be read") from exc
    if not isinstance(manifest, dict) or type(manifest.get("schema")) is not int or manifest["schema"] != 1:
        raise ValueError("unsupported manifest schema")
    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("invalid release version")
    sequence = manifest.get("sequence")
    if type(sequence) is not int or sequence <= 0:
        raise ValueError("invalid release sequence")
    path = manifest.get("path")
    expected_name = "agent_core_" + version.replace(".", "_") + ".py"
    if not isinstance(path, str) or path != expected_name:
        raise ValueError("release path does not match version or is not a direct engine filename")
    expected_size = manifest.get("size_bytes")
    if type(expected_size) is not int or not 0 < expected_size <= LEGACY_LIMIT:
        raise ValueError("release violates legacy updater size limit")
    expected_sha = manifest.get("sha256")
    if not isinstance(expected_sha, str) or not HEX_SHA256.fullmatch(expected_sha):
        raise ValueError("manifest SHA-256 is invalid")
    try:
        payload = (directory / path).read_bytes()
    except OSError as exc:
        raise ValueError("published engine is missing or unreadable") from exc
    if len(payload) != expected_size:
        raise ValueError("published engine byte size does not match manifest")
    actual_sha = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha, expected_sha):
        raise ValueError("published engine SHA-256 does not match manifest")
    try:
        source = payload.decode("utf-8")
        tree = ast.parse(source, filename=str(directory / path))
        compile(tree, str(directory / path), "exec")
    except (UnicodeError, SyntaxError, ValueError) as exc:
        raise ValueError("published engine fails encoding or Python syntax check") from exc
    assigned_versions = [
        node.value.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    ]
    if len(assigned_versions) != 1 or assigned_versions[0].split("-", 1)[0] != version:
        raise ValueError("engine's VERSION does not match manifest")
    return {"version": version, "sequence": sequence, "path": path,
            "size_bytes": len(payload), "sha256": actual_sha}


class ActiveReleaseContractTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = "VERSION = '2.3.4-deepseek-flash'\n\ndef main():\n    return True\n"
        self.manifest = {"schema": 1, "sequence": 234, "version": "2.3.4",
                         "path": "agent_core_2_3_4.py", "summary": "fixture"}
        self.write_fixture()

    def write_fixture(self):
        payload = self.source.encode("utf-8")
        (self.root / self.manifest["path"]).write_bytes(payload)
        self.manifest["size_bytes"] = len(payload)
        self.manifest["sha256"] = hashlib.sha256(payload).hexdigest()
        (self.root / "manifest.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def test_valid_release(self):
        self.assertEqual(validate_active_release(self.root)["version"], "2.3.4")

    def test_changed_binary_rejected(self):
        (self.root / self.manifest["path"]).write_bytes(b"X" + self.source.encode()[1:])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_active_release(self.root)

    def test_mismatched_length_rejected(self):
        self.manifest["size_bytes"] += 1
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "byte size"):
            validate_active_release(self.root)

    def test_legacy_limit_rejected(self):
        self.manifest["size_bytes"] = LEGACY_LIMIT + 1
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "legacy updater"):
            validate_active_release(self.root)

    def test_unsafe_manifest_path_rejected(self):
        self.manifest["path"] = "../agent_core_2_3_4.py"
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "release path"):
            validate_active_release(self.root)

    def test_wrong_source_version_even_with_valid_hash(self):
        self.source = self.source.replace("2.3.4-deepseek-flash", "2.3.3-deepseek-flash")
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "VERSION"):
            validate_active_release(self.root)

    def test_syntax_error_even_with_valid_hash(self):
        self.source = "VERSION = '2.3.4-deepseek-flash'\ndef broken(:\n    pass\n"
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "syntax"):
            validate_active_release(self.root)

    def test_duplicate_manifest_keys_rejected(self):
        raw = (self.root / "manifest.json").read_text(encoding="utf-8")
        (self.root / "manifest.json").write_text(
            raw.replace('"schema": 1,', '"schema": 1, "schema": 1,'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            validate_active_release(self.root)

    def test_current_published_engine(self):
        if not (PROJECT / "manifest.json").is_file():
            self.skipTest("project files unavailable in isolated test workspace")
        self.assertLessEqual(validate_active_release(PROJECT)["size_bytes"], LEGACY_LIMIT)


if __name__ == "__main__":
    unittest.main()
