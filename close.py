#!/usr/bin/env python3
"""Ask the nb window's Neovim to quit, preserving its unsaved-changes prompt."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def descendants(pid):
    pending = [pid]
    seen = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            for task in Path(f"/proc/{current}/task").iterdir():
                pending.extend(int(child) for child in (task / "children").read_text().split())
        except OSError:
            pass
    return seen


def close_window(pid, token):
    if pid <= 0 or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Expected a window PID and omanb session token")
    app_id = f"org.omarchy.omanb.{token}"
    result = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True,
                            text=True, check=True, timeout=5)
    if not any(window.get("pid") == pid and window.get("class") == app_id
               for window in json.loads(result.stdout)):
        return

    marker = f"OMANB_SESSION_TOKEN={token}".encode()
    editors = set()
    for child in descendants(pid):
        try:
            if (Path(f"/proc/{child}/comm").read_text().strip() == "nvim"
                    and marker in Path(f"/proc/{child}/environ").read_bytes().split(b"\0")):
                editors.add(child)
        except OSError:
            pass

    if not editors:
        # nb's interactive shell has no editor buffer requiring a save prompt.
        subprocess.run(["hyprctl", "eval", f'local w = hl.get_active_window(); if w and w.pid == {pid} and w.class == "{app_id}" then hl.dispatch(hl.dsp.window.close()) end'], check=True, timeout=5)
        return

    for line in Path("/proc/net/unix").read_text().splitlines():
        fields = line.split(maxsplit=7)
        if len(fields) != 8:
            continue
        socket = Path(fields[7])
        match = re.fullmatch(r"nvim\.(\d+)\.\d+", socket.name)
        if not match or int(match[1]) not in editors:
            continue
        try:
            if socket.stat().st_uid != os.getuid():
                continue
            subprocess.run(["nvim", "--server", str(socket), "--remote-send",
                            "<C-\\><C-N>:confirm qall<CR>"], check=True, timeout=5)
            return
        except (OSError, subprocess.SubprocessError):
            continue
    subprocess.run(["notify-send", "omanb", "Could not reach Neovim. Use :confirm qall in the editor to save or discard changes."], check=False)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: close.py <window-pid> <session-token>")
    try:
        close_window(int(sys.argv[1]), sys.argv[2])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        subprocess.run(["notify-send", "omanb", f"Could not close the note: {error}"], check=False)
        raise SystemExit(str(error))
