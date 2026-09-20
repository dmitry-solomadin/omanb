"""Check that stale Neovim sockets do not interrupt the save-prompt fallback."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("close_helper", Path(__file__).resolve().parents[1] / "close.py")
close = importlib.util.module_from_spec(spec)
spec.loader.exec_module(close)


class CloseEditor(unittest.TestCase):
    token = "a" * 32

    def read_text(self, path):
        if str(path).endswith("/comm"):
            return "nvim\n"
        return "\n".join(f"0: 0 0 0 0 0 0 /tmp/nvim.42.{index}" for index in range(2))

    def run_close(self, outcomes, clients=None, environments=None):
        if clients is None:
            clients = [{"pid": 10, "class": "org.omarchy.omanb." + self.token}]
        if environments is None:
            environments = {42: ("OMANB_SESSION_TOKEN=" + self.token).encode()}
        client_result = subprocess.CompletedProcess([], 0, stdout=json.dumps(clients))
        with patch.object(close, "descendants", return_value=set(environments)), \
              patch.object(close.Path, "read_text", lambda path: self.read_text(path)), \
             patch.object(close.Path, "read_bytes", lambda path: environments[int(path.parts[2])]), \
              patch.object(close.Path, "stat", return_value=SimpleNamespace(st_uid=os.getuid())), \
             patch.object(close.subprocess, "run", side_effect=[client_result, *outcomes]) as run:
            close.close_window(10, self.token)
        return [call.args[0] for call in run.call_args_list[1:]]

    def test_failed_socket_tries_next_editor_socket(self):
        commands = self.run_close([subprocess.CalledProcessError(1, "nvim"), None])
        self.assertEqual([command[2] for command in commands], ["/tmp/nvim.42.0", "/tmp/nvim.42.1"])
        self.assertTrue(all(":confirm qall" in command[-1] for command in commands))

    def test_unreachable_editor_notifies_without_closing_window(self):
        commands = self.run_close([subprocess.TimeoutExpired("nvim", 5), OSError("stale socket"), None])
        self.assertEqual(commands[-1][0], "notify-send")
        self.assertNotIn("hyprctl", [command[0] for command in commands])

    def test_ordinary_terminal_is_ignored(self):
        self.assertEqual(self.run_close([], clients=[{"pid": 10, "class": "com.mitchellh.ghostty"}]), [])

    def test_missing_window_is_ignored(self):
        self.assertEqual(self.run_close([], clients=[]), [])

    def test_only_matching_session_can_receive_remote_command(self):
        # Both Neovims belong to one shared terminal PID; only 43 has our token.
        commands = self.run_close([None], environments={42: b"OTHER=normal", 43: ("OMANB_SESSION_TOKEN=" + self.token).encode()})
        # The available socket belongs to unrelated editor 42, so leave it alone.
        self.assertEqual([command[0] for command in commands], ["notify-send"])

    def test_empty_plugin_terminal_uses_guarded_close(self):
        commands = self.run_close([None], environments={})
        self.assertEqual(commands[0][:2], ["hyprctl", "eval"])
        self.assertIn("org.omarchy.omanb." + self.token, commands[0][2])
        self.assertIn("w.pid == 10", commands[0][2])
