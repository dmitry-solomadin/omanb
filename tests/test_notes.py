"""Exercise the helper CLI without accessing the user's nb notebooks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HELPER = Path(__file__).resolve().parents[1] / "notes.py"
FAKE_NB = '''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_NOTEBOOK"])
args = sys.argv[1:]
if os.environ.get("TEST_NB_ERROR"):
    sys.stderr.write("Notebook unavailable")
    sys.exit(1)
if args[:2] == ["notebooks", "current"]:
    print("" if os.environ.get("TEST_EMPTY_PATH") else root)
elif args[:2] == ["notebooks", "show"]:
    assert args[2] == str(root)
    print("test")
elif args[0] == "list":
    folder = root / args[1].split(":", 1)[1]
    for path in sorted(folder.glob("*.md")):
        print(path)
elif args[0] == "delete":
    assert os.environ["NB_AUTO_SYNC"] == "0"
    assert args[2] == "--force"
    (root / args[1].split(":", 1)[1]).unlink()
else:
    raise SystemExit("Unexpected command: " + repr(args))
'''


class NotesCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omanb-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.notebook = self.root / "notebook"
        self.notebook.mkdir()
        (self.notebook / ".index").touch()
        executable = self.root / "nb"
        executable.write_text(FAKE_NB)
        executable.chmod(0o755)
        launcher = self.root / "omarchy-launch-tui"
        launcher.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        launcher.chmod(0o755)
        notifier = self.root / "notify-send"
        notifier.write_text('#!/bin/sh\nexit 0\n')
        notifier.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                    "TEST_NOTEBOOK": str(self.notebook)}

    def run_helper(self, *args):
        result = subprocess.run([sys.executable, str(HELPER), *args], env=self.env,
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_empty_notebook(self):
        self.assertEqual(self.run_helper("list"), {"notebook": "test", "notes": [], "error": ""})

    def test_nested_notes_sorted_and_external_symlink_excluded(self):
        older = self.notebook / "old.md"
        older.write_text("# Old\nOld preview")
        os.utime(older, (100, 100))
        folder = self.notebook / "sub folder"
        folder.mkdir()
        (folder / ".index").touch()
        newer = folder / "new note.md"
        newer.write_text("# New\nNew preview")
        os.utime(newer, (200, 200))
        external = self.root / "private.md"
        external.write_text("Do not include")
        (self.notebook / "external.md").symlink_to(external)
        notes = self.run_helper("list")["notes"]
        self.assertEqual([note["title"] for note in notes], ["New", "Old"])
        self.assertEqual(notes[0]["selector"], "test:sub folder/new note.md")
        self.assertEqual(notes[0]["preview"], "New preview")

    def test_stale_selector_does_not_delete_other_note(self):
        note = self.notebook / "keep.md"
        note.write_text("# Keep")
        result = self.run_helper("delete", "test:missing.md")
        self.assertIn("no longer", result["error"])
        self.assertTrue(note.exists())

    def test_delete_exact_note_with_spaces(self):
        note = self.notebook / "a note.md"
        note.write_text("# Delete me")
        self.assertEqual(self.run_helper("delete", "test:a note.md"), {"error": ""})
        self.assertFalse(note.exists())

    def test_nb_failure_is_structured_error(self):
        self.env["TEST_NB_ERROR"] = "1"
        result = self.run_helper("list")
        self.assertEqual(result["notes"], [])
        self.assertEqual(result["error"], "Notebook unavailable")

    def test_missing_nb_is_structured_error(self):
        (self.root / "nb").unlink()
        self.env.update(PATH=str(self.root), HOME=str(self.root))
        result = self.run_helper("list")
        self.assertEqual(result["notes"], [])
        self.assertIn("nb is not installed", result["error"])

    def test_terminal_launch_preserves_selector_as_one_argument(self):
        folder = self.notebook / "sub folder"
        folder.mkdir()
        (folder / ".index").touch()
        (folder / "a; note.md").write_text("# A note")
        selector = "test:sub folder/a; note.md"
        command = self.run_helper("edit", selector)
        self.assertRegex(command[0], r"^--app-id=org\.omarchy\.omanb\.s[0-9a-f]{32}$")
        self.assertEqual(command[1], "env")
        self.assertEqual(command[2], "OMANB_SESSION_TOKEN=" + command[0].rsplit(".", 1)[1][1:])
        self.assertEqual(command[3:], [str(self.root / "nb"), "edit", selector])
        self.assertEqual(self.run_helper("new", "another notebook")[-2:],
                         ["add", "another notebook:"])

    def test_stale_edit_does_not_launch_terminal(self):
        (self.notebook / "keep.md").write_text("# Keep")
        result = subprocess.run([sys.executable, str(HELPER), "edit", "test:missing.md"],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("no longer", result.stderr)

    def test_empty_notebook_path_is_not_current_directory(self):
        self.env["TEST_EMPTY_PATH"] = "1"
        result = self.run_helper("list")
        self.assertEqual(result["notes"], [])
        self.assertIn("No current nb notebook", result["error"])

    def test_hashtag_title_preserved(self):
        (self.notebook / "hashtag.md").write_text("#project ideas\nA preview")
        self.assertEqual(self.run_helper("list")["notes"][0]["title"], "#project ideas")

    def test_invalid_arguments_do_not_launch(self):
        for args in [("edit",), ("delete",), ("shell", "extra"), ("new", "one", "two")]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(HELPER), *args],
                                        env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
