#!/usr/bin/env python3
"""List/delete nb notes; launch creation and editing in a terminal."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\([A-Z])")


def nb_executable():
    executable = shutil.which("nb") or Path.home() / ".local/bin/nb"
    if not os.access(executable, os.X_OK):
        raise RuntimeError("nb is not installed. Install nb and initialize a notebook first.")
    return str(executable)


def nb(*args):
    result = subprocess.run(
        [nb_executable(), *args],
        text=True, capture_output=True, timeout=15,
        env={**os.environ, "NB_AUTO_SYNC": "0"},
    )
    if result.returncode:
        raise RuntimeError(ANSI.sub("", result.stderr or result.stdout).strip() or "nb failed")
    return ANSI.sub("", result.stdout).strip()


def read_note(path, notebook, name):
    relative = path.relative_to(notebook)
    if not path.resolve().is_relative_to(notebook):
        return None
    with path.open(encoding="utf-8", errors="replace") as source:
        lines = [line.strip() for line in source.read(8192).splitlines() if line.strip()]
    title = re.sub(r"^#+\s+", "", lines[0]) if lines else path.stem
    return {"selector": f"{name}:{relative.as_posix()}",
            "title": title[:160], "file": relative.as_posix(),
            "preview": "\n".join(lines[1:])[:1000],
            "modified": path.stat().st_mtime}


def snapshot():
    notebook = Path(nb("notebooks", "current", "--path"))
    if not notebook.is_absolute() or not notebook.is_dir():
        raise RuntimeError("No current nb notebook. Open the nb shell to set one up.")
    # Resolve the name from the captured path, even if the user switches notebooks.
    name = nb("notebooks", "show", str(notebook), "--name")
    notebook = notebook.resolve()
    notes = []
    # Ask nb for its note paths in each indexed folder, preserving nb's file typing.
    for directory, subdirs, files in os.walk(notebook):
        subdirs[:] = sorted(entry for entry in subdirs if entry != ".git")
        folder = Path(directory)
        if folder != notebook and ".index" not in files:
            continue
        relative = folder.relative_to(notebook).as_posix()
        selector = name + ":" + (relative + "/" if relative != "." else "")
        for line in nb("list", selector, "--paths", "--no-id", "--all", "--type", "note").splitlines():
            path = Path(line)
            if not path.is_absolute() or not path.is_file():
                continue  # Empty-notebook help output is not a path.
            try:
                note = read_note(path, notebook, name)
                if note:
                    notes.append(note)
            except (OSError, ValueError):
                continue  # A note can disappear while an editor is saving it.
    notes.sort(key=lambda note: note["modified"], reverse=True)
    return {"notebook": name, "notes": notes, "error": ""}


def require_note(selector):
    # nb accepts fuzzy selectors; stale UI entries must not target another note.
    if not any(note["selector"] == selector for note in snapshot()["notes"]):
        raise RuntimeError("This note is no longer in the current notebook. Refresh and try again.")


def perform(action, selector):
    if action == "list":
        return snapshot()
    if action in ("edit", "delete"):
        require_note(selector)
    if action == "delete":
        nb("delete", selector, "--force")
        return {"error": ""}

    command = {"new": "add", "edit": "edit", "shell": "shell"}[action]
    if action == "new" and selector:
        selector += ":"
    arguments = [selector] if selector else []
    token = uuid.uuid4().hex
    # Pass the marker inside the terminal command, including for shared terminal servers.
    os.execvp("omarchy-launch-tui", ["omarchy-launch-tui", f"--app-id=org.omarchy.omanb.{token}",
                                   "env", f"OMANB_SESSION_TOKEN={token}",
                                   nb_executable(), command, *arguments])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="list", choices=("list", "delete", "edit", "new", "shell"))
    parser.add_argument("selector", nargs="?")
    args = parser.parse_args()
    if args.action in ("edit", "delete") and not args.selector:
        parser.error(f"{args.action} requires a note selector")
    if args.action in ("list", "shell") and args.selector is not None:
        parser.error(f"{args.action} does not accept a selector")

    data = {"error": ""}
    if args.action == "list":
        data.update(notebook="", notes=[])
    try:
        data = perform(args.action, args.selector)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        data["error"] = str(error)
        if args.action not in ("list", "delete"):
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", "omanb", str(error)], check=False)
            raise SystemExit(str(error))
    print(json.dumps(data))


if __name__ == "__main__":
    main()
