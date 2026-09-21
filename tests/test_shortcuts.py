"""Test conflict detection and execute binding lifecycle scripts in a fake Lua host."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest


spec = importlib.util.spec_from_file_location("shortcuts", Path(__file__).resolve().parents[1] / "shortcuts.py")
shortcuts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shortcuts)
COMMANDS = (
    (64, "SUPER + N", "open", ["omarchy-shell", "shell", "toggle", "test.omanb"]),
    (72, "SUPER + ALT + N", "new", ["python3", "/path with spaces/notes.py", "new"]),
)
HOST = """
  local active = {}
  hl = { dsp = { exec_cmd = function(command) return command end } }
  function hl.bind(keys, command, options)
    local handle = { keys = keys, command = command }
    active[handle] = true
    function handle:remove() active[self] = nil end
    return handle
  end
  local function count()
    local n = 0
    for _ in pairs(active) do n = n + 1 end
    return n
  end
"""


class Conflicts(unittest.TestCase):
    def test_each_combination_checked_independently(self):
        bindings = [{"modmask": 64, "key": "n"}]
        self.assertTrue(shortcuts.occupied(bindings, 64))
        self.assertFalse(shortcuts.occupied(bindings, 72))
        script = shortcuts.install_script("one", "test.omanb", COMMANDS, bindings)
        self.assertNotIn("SUPER + N", script)
        self.assertIn("SUPER + ALT + N", script)

    def test_release_physical_submap_and_catchall_bindings_block(self):
        for binding in [{"key": "N", "release": True}, {"keycode": 57},
                        {"key": "N", "submap": "custom"}, {"catch_all": True}]:
            with self.subTest(binding=binding):
                self.assertTrue(shortcuts.occupied([{**binding, "modmask": 64}], 64))

    def test_other_keys_and_modifiers_do_not_block(self):
        self.assertFalse(shortcuts.occupied([{"modmask": 65, "key": "N"},
                                             {"modmask": 64, "key": "M"}], 64))


@unittest.skipUnless(shutil.which("lua"), "Lua is required for shortcut lifecycle tests")
class Lifecycle(unittest.TestCase):
    def run_lua(self, *scripts):
        result = subprocess.run(["lua", "-"], input=HOST + "\n".join(scripts),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def install(self, token):
        return shortcuts.install_script(token, "test.omanb", COMMANDS, [])

    def test_register_and_remove_only_owned_bindings(self):
        self.run_lua(self.install("one"), "assert(count() == 2)",
                     'hl.bind("SUPER + N", "user command", {})',
                     'omanb_release_shortcuts("one")', "assert(count() == 1)")

    def test_overlapping_reload_keeps_bindings_until_last_owner_exits(self):
        self.run_lua(self.install("old"), self.install("new"), "assert(count() == 2)",
                     'omanb_release_shortcuts("old")', "assert(count() == 2)",
                     'omanb_release_shortcuts("new")', "assert(count() == 0)")

    def test_destruction_before_install_cancels_registration(self):
        self.run_lua('_G.omanb_shortcut_cancellations = { gone = true }',
                     self.install("gone"), "assert(count() == 0)")

    def test_repeated_install_does_not_duplicate(self):
        self.run_lua(self.install("one"), self.install("one"), "assert(count() == 2)")

    def test_configuration_reload_can_register_again(self):
        self.run_lua(self.install("one"),
                     'active = {}; _G.omanb_shortcut_groups = nil; _G.omanb_shortcut_cancellations = nil',
                     self.install("one"), "assert(count() == 2)")

    def test_lua_strings_preserve_quotes_unicode_and_delimiters(self):
        value = 'quote " café ]] ]=] newline\nend'
        self.run_lua("local text = " + shortcuts.lua_string(value),
                     'assert(text:find("café", 1, true)); assert(text:find("]=]", 1, true))')


@unittest.skipUnless(shutil.which("lua"), "Lua is required for close-shortcut tests")
class SavePrompt(unittest.TestCase):
    run_lua = Lifecycle.run_lua

    setup = """
      local registry = debug.getregistry()
      local calls = 0
      local ran = nil
      local window = nil
      local original = function(value) calls = calls + 1; return value end
      registry[9999] = original
      hl.get_active_window = function() return window end
      hl.exec_cmd = function(command) ran = command end
    """

    def close_install(self, token="close"):
        bindings = [{"modmask": 64, "key": "W", "dispatcher": "__lua", "arg": "9999"}]
        return shortcuts.install_script(token, "test.omanb", [], bindings, Path("/plugin directory"))

    def test_regular_neovim_preserves_original_action(self):
        self.run_lua(self.setup, self.close_install(),
                     'window = { class = "org.omarchy.nvim", pid = 1 }',
                     'assert(registry[9999]("original result") == "original result")',
                     'assert(calls == 1 and ran == nil)')

    def test_plugin_window_routes_to_its_session_only(self):
        token = "0" * 32
        self.run_lua(self.setup, self.close_install(),
                     f'window = {{ class = "org.omarchy.omanb.s{token}", pid = 42 }}',
                     'registry[9999]()', 'assert(calls == 0)',
                     f'assert(ran == "python3 \'/plugin directory/close.py\' 42 {token}")')

    def test_disabling_restores_original_close(self):
        self.run_lua(self.setup, self.close_install(),
                     'omanb_release_shortcuts("close")', 'assert(registry[9999] == original)')

    def test_user_replacement_is_preserved_on_disable(self):
        self.run_lua(self.setup, self.close_install(),
                     'local replacement = function() end; registry[9999] = replacement',
                     'omanb_release_shortcuts("close")', 'assert(registry[9999] == replacement)')

    def test_hot_reload_does_not_double_wrap_or_restore_too_early(self):
        self.run_lua(self.setup, self.close_install("old"), self.close_install("new"),
                     'omanb_release_shortcuts("old")', 'assert(registry[9999] ~= original)',
                      'omanb_release_shortcuts("new")', 'assert(registry[9999] == original)')

    def test_unknown_binding_formats_leave_close_and_open_new_working(self):
        for binding in [{"dispatcher": "killactive", "arg": ""},
                        {"dispatcher": "__lua_v2", "arg": "9999"},
                        {"dispatcher": "__lua", "arg": "callback:9999"},
                        {"dispatcher": "__lua", "arg": "0"},
                        {"dispatcher": "__lua", "arg": "9" * 5000}]:
            with self.subTest(binding=binding):
                script = shortcuts.install_script("close", "test.omanb", COMMANDS,
                    [{"modmask": 64, "key": "W", **binding}], Path("/plugin"))
                self.run_lua(self.setup, script,
                             'assert(count() == 2 and registry[9999] == original)')

    def test_missing_or_changed_registry_skips_optional_integration(self):
        for change in ['debug = nil', 'debug.getregistry = nil',
                       'debug.getregistry = function() error("API changed") end',
                       'debug.getregistry = function() return false end',
                       'registry[9999] = { callback = original }',
                       'hl.get_active_window = nil', 'hl.exec_cmd = nil']:
            with self.subTest(change=change):
                script = shortcuts.install_script("close", "test.omanb", COMMANDS,
                    [{"modmask": 64, "key": "W", "dispatcher": "__lua", "arg": "9999"}], Path("/plugin"))
                self.run_lua(self.setup, change, 'local before = registry[9999]', script,
                             'assert(count() == 2 and registry[9999] == before)',
                             'omanb_release_shortcuts("close")', 'assert(count() == 0)')

    def test_all_close_callbacks_checked_before_wrapping(self):
        bindings = [{"modmask": 64, "key": "W", "dispatcher": "__lua", "arg": str(ref)}
                    for ref in (9999, 9998)]
        script = shortcuts.install_script("close", "test.omanb", COMMANDS, bindings, Path("/plugin"))
        self.run_lua(self.setup, 'registry[9998] = nil', script,
                     'assert(registry[9999] == original and count() == 2)')

    def test_runtime_api_failures_fall_back_to_original_once(self):
        for change in ['hl.get_active_window = nil',
                       'hl.get_active_window = function() error("API changed") end',
                       'window = { class = 123 }',
                       'window.pid = nil', 'window.pid = "42"', 'window.pid = -1',
                       'hl.exec_cmd = nil',
                       'hl.exec_cmd = function() error("API changed") end',
                       'hl.exec_cmd = function() return false end']:
            with self.subTest(change=change):
                self.run_lua(self.setup, self.close_install(),
                    'window = { class = "org.omarchy.omanb.s' + '0' * 32 + '", pid = 42 }',
                    change, 'assert(registry[9999]("result") == "result")',
                    'assert(calls == 1 and ran == nil)',
                    'omanb_release_shortcuts("close")', 'assert(registry[9999] == original)')

    def test_original_arguments_returns_and_errors_are_preserved(self):
        self.run_lua(self.setup,
                     'original = function(...) calls = calls + 1; return ... end; registry[9999] = original',
                     self.close_install(), 'hl.get_active_window = nil',
                     'local a, b, c = registry[9999]("first", nil, "third")',
                     'assert(a == "first" and b == nil and c == "third" and calls == 1)')
        self.run_lua(self.setup,
                     'registry[9999] = function() calls = calls + 1; error("original failure") end',
                     self.close_install(), 'hl.get_active_window = nil',
                     'local ok, err = pcall(registry[9999])',
                     'assert(not ok and err:find("original failure", 1, true) and calls == 1)')

    def test_unbound_close_uses_public_default_on_runtime_failure(self):
        script = shortcuts.install_script("close", "test.omanb", [], [], Path("/plugin"))
        self.run_lua(self.setup,
                     'hl.dsp.window = { close = function() return "default close" end }',
                     'hl.dispatch = function(action) assert(action == "default close"); calls = calls + 1 end',
                     script, 'assert(count() == 1)', 'hl.get_active_window = nil',
                     'for handle in pairs(active) do handle.command() end',
                     'assert(calls == 1)', 'omanb_release_shortcuts("close")', 'assert(count() == 0)')
