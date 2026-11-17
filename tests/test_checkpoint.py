import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from takeout.bundle import CheckpointError, digest, dumps, export_checkpoint, prepare, verify
from takeout.source import CodexSource


SOURCE = {"thread": {"id": "fixture", "turns": [{"id": "turn1", "items": [
    {"id": "item1", "type": "userMessage", "content": [{"type": "text", "text": "Finish the parser"}]},
    {"id": "item2", "type": "futureUnknownType", "payload": {"preserve": True}}]}]}}


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.output = self.base / "checkpoint"

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL)

    def export(self):
        return export_checkpoint(SOURCE, self.root, self.output, "Finish parser", "Fix the failing check")

    def test_git_roundtrip_staged_unstaged_binary_deleted_and_untracked(self):
        self.git("init")
        (self.root / "file").write_text("baseline\n")
        (self.root / "deleted").write_text("gone\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@localhost", "-c", "commit.gpgsign=false", "commit", "-m", "baseline")
        (self.root / "file").write_text("staged\n")
        self.git("add", "file")
        (self.root / "file").write_text("unstaged\n")
        (self.root / "deleted").unlink()
        (self.root / "binary").write_bytes(b"\x00\xff\x01")
        (self.root / ".env").write_text("do not export")
        (self.root / "link").symlink_to("file")
        (self.root / "run").write_text("exit 0\n")
        (self.root / "run").chmod(0o755)
        self.export()
        target = self.base / "restored"
        prepare(self.output, target, "gemini-cli")
        work = target / "workspace"
        self.assertEqual((work / "file").read_text(), "unstaged\n")
        self.assertEqual(subprocess.check_output(["git", "-C", str(work), "show", ":file"]), b"staged\n")
        self.assertFalse((work / "deleted").exists())
        self.assertEqual((work / "binary").read_bytes(), b"\x00\xff\x01")
        self.assertFalse((work / ".env").exists())
        self.assertFalse((work / "link").exists())
        self.assertTrue((work / "run").stat().st_mode & 0o100)
        events = (self.output / "threads/fixture/events.jsonl").read_text()
        self.assertIn("futureUnknownType", events)
        self.assertTrue((target / "GEMINI.md").exists())

    def test_tampering_and_unlisted_files_rejected(self):
        (self.root / "a").write_text("hello")
        self.export()
        (self.output / "START_HERE.md").write_text("tampered")
        with self.assertRaises(CheckpointError):
            verify(self.output)
        with self.assertRaises(CheckpointError):
            prepare(self.output, self.base / "restore")
        self.assertFalse((self.base / "restore").exists())

    def test_traversal_even_with_updated_manifest_is_rejected(self):
        self.export()
        meta_path = self.output / "workspaces/main/workspace.json"
        meta = json.loads(meta_path.read_text())
        meta["files"]["working"]["../escape"] = {"path": "START_HERE.md", "mode": "100644"}
        meta_path.write_text(dumps(meta))
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        data = meta_path.read_bytes()
        manifest["files"]["workspaces/main/workspace.json"] = {"sha256": digest(data), "size": len(data)}
        manifest_path.write_text(dumps(manifest))
        with self.assertRaises(CheckpointError):
            prepare(self.output, self.base / "restore")

    def test_secret_and_unsafe_destination_rejected(self):
        (self.root / "secret").write_text("ghp_" + "a" * 36)
        with self.assertRaises(CheckpointError):
            self.export()
        self.assertFalse(self.output.exists())
        (self.root / "secret").unlink()
        with self.assertRaises(CheckpointError):
            export_checkpoint(SOURCE, self.root, self.root / "nested")
        self.export()
        with self.assertRaises(CheckpointError):
            prepare(self.output, self.root)

    def test_pagination_consumed_and_repeated_cursor_rejected(self):
        source = object.__new__(CodexSource)
        calls = []
        def call(method, params):
            calls.append(params.copy())
            return {"data": [len(calls)], "nextCursor": "second" if len(calls) == 1 else None}
        source.call = call
        self.assertEqual(list(source.pages("thread/list", {})), [1, 2])
        self.assertEqual(calls[1]["cursor"], "second")
        source.call = lambda *args: {"data": [], "nextCursor": "loop"}
        with self.assertRaises(RuntimeError):
            list(source.pages("thread/list", {}))


if __name__ == "__main__":
    unittest.main()
