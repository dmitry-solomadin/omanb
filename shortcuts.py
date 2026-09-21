#!/usr/bin/env python3
"""Register unused Hyprland shortcuts and remove only this instance's bindings."""
import json
from pathlib import Path
import shlex
import subprocess
import sys


BOOTSTRAP = """
  _G.omanb_shortcut_groups = _G.omanb_shortcut_groups or {}
  _G.omanb_shortcut_cancellations = _G.omanb_shortcut_cancellations or {}
  function _G.omanb_release_shortcuts(token)
    _G.omanb_shortcut_cancellations[token] = true
    for _, group in pairs(_G.omanb_shortcut_groups) do
      group.owners[token] = nil
      if not next(group.owners) then
        for _, handle in pairs(group.handles) do
          pcall(function() handle:remove() end)
        end
        group.handles = {}
      end
    end
  end
"""


def hyprctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True,
                            check=True, timeout=5)
    if args[0] == "eval" and result.stdout.strip() != "ok":
        raise RuntimeError(result.stdout.strip())
    return result.stdout


def lua_string(text):
    equals = ""
    while "]" + equals + "]" in text:
        equals += "="
    return "[" + equals + "[" + text + "]" + equals + "]"


def occupied(bindings, mask):
    # Include release/repeat/submap bindings and physical-key bindings for N.
    return any(
        (binding.get("modmask") == mask or binding.get("ignore_mods", False))
        and (binding.get("key", "").lower() in ("n", "code:57")
             or binding.get("keycode") == 57 or binding.get("catch_all", False))
        for binding in bindings
    )


def close_script(directory, bindings):
    matches = [binding for binding in bindings
               if binding.get("modmask") == 64
               and (binding.get("key", "").lower() in ("w", "code:25") or binding.get("keycode") == 25)]
    # Unknown binding formats must not prevent the open/new shortcuts installing.
    references = []
    for binding in matches:
        reference = str(binding.get("arg", ""))
        if (binding.get("dispatcher") != "__lua" or len(reference) > 10 or not reference.isascii()
                or not reference.isdecimal() or not 0 < int(reference) <= 2147483647):
            return ""
        references.append(int(reference))

    command = lua_string(shlex.join(["python3", str(directory / "close.py")]))
    script = f"""
    -- Save-on-close is optional; compatibility failures leave normal closing intact.
    pcall(function()
      if type(hl.get_active_window) ~= "function" or type(hl.exec_cmd) ~= "function" then return end
      local function close_note(original, ...)
        local ok, handled = pcall(function()
          local window = hl.get_active_window()
          if not window or type(window.class) ~= "string" then return false end
          local session = window.class:match("^org%.omarchy%.omanb%.s([0-9a-f]+)$")
          if not session or #session ~= 32 then return false end
          local pid = window.pid
          if type(pid) ~= "number" or pid <= 0 or pid % 1 ~= 0 then return false end
          if hl.exec_cmd({command} .. " " .. string.format("%.0f", pid) .. " " .. session) == false then return false end
          return true
        end)
        if ok and handled then return end
        -- Keep the original outside pcall: never swallow its errors or call it twice.
        return original(...)
      end
    """
    if not matches:
        return script + """
          if not group.handles.close then
            group.handles.close = hl.bind("SUPER + W", function()
              return close_note(function() hl.dispatch(hl.dsp.window.close()) end)
            end, { description = "Close window (omanb: ask to save)" })
          end
        end)
        """

    # Lua bindings call their registry function by reference. Wrapping that function
    # preserves the user's key, flags, ordering, and original non-omanb action.
    script += """
      if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then return end
      local registry = debug.getregistry()
      if type(registry) ~= "table" then return end
    """
    # Preflight every target before changing any callback, including duplicate binds.
    for reference in references:
        script += f'\n      if type(rawget(registry, {reference})) ~= "function" then return end\n'
    for reference in dict.fromkeys(references):
        script += f"""
          do
            local ref = {reference}
            local key = "close:" .. ref
            local previous = group.handles[key]
            if not previous or rawget(registry, ref) ~= previous.callback then
              local original = rawget(registry, ref)
              local wrapper = function(...) return close_note(original, ...) end
              rawset(registry, ref, wrapper)
              group.handles[key] = {{
                callback = wrapper,
                remove = function()
                  if rawget(registry, ref) == wrapper then rawset(registry, ref, original) end
                end
              }}
            end
          end
        """
    return script + "\nend)"


def install_script(token, plugin_id, commands, bindings, directory=None):
    # Overlapping shell generations share handles until their last owner exits.
    script = BOOTSTRAP + f"""
      local token = {lua_string(token)}
      local id = {lua_string(plugin_id)}
      if not _G.omanb_shortcut_cancellations[token] then
        local group = _G.omanb_shortcut_groups[id] or {{ owners = {{}}, handles = {{}} }}
        _G.omanb_shortcut_groups[id] = group
        group.owners[token] = true
    """
    for mask, keys, description, command in commands:
        if not occupied(bindings, mask):
            key = lua_string(keys)
            script += f"""
              if group.handles[ {key} ] then
                pcall(function() group.handles[ {key} ]:remove() end)
              end
              group.handles[ {key} ] = hl.bind({key},
                hl.dsp.exec_cmd({lua_string(shlex.join(command))}),
                {{ description = {lua_string(description)} }})
            """
    if directory is not None:
        script += close_script(directory, bindings)
    return script + "\nend"


def install(token):
    directory = Path(__file__).resolve().parent
    plugin_id = json.loads((directory / "manifest.json").read_text())["id"]
    bindings = json.loads(hyprctl("-j", "binds"))
    commands = (
        (64, "SUPER + N", "omanb: open notes", ["omarchy-shell", "shell", "toggle", plugin_id]),
        (72, "SUPER + ALT + N", "omanb: new note", ["python3", str(directory / "notes.py"), "new"]),
    )
    hyprctl("eval", install_script(token, plugin_id, commands, bindings, directory))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: shortcuts.py <instance-token>")
    try:
        install(sys.argv[1])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"omanb shortcuts: {error}")
