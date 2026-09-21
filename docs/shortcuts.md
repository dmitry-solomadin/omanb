# Shortcuts

omanb automatically registers **Super+N** (open notes) and **Super+Alt+N** (new note) when each combination is unused. It checks on enable and after Hyprland configuration reloads, and removes only its own bindings when disabled or removed. It does not write to your Hyprland configuration. Requires Hyprland's Lua API.

## Custom bindings

For Omarchy's Lua-based Hyprland configuration, add the following to `~/.config/hypr/bindings.lua` to choose your own keys or add the optional nb-shell shortcut. Existing manual bindings are left alone by the automatic setup.

```lua
local omanb = 'python3 "' .. os.getenv("HOME") .. '/.config/omarchy/plugins/io.github.dmitry-solomadin.omanb/notes.py" '
o.bind("SUPER + N", "omanb: dropdown", "omarchy-shell shell toggle io.github.dmitry-solomadin.omanb")
o.bind("SUPER + ALT + N", "omanb: new note", omanb .. "new")
o.bind("SUPER + CTRL + SHIFT + N", "omanb: nb shell", omanb .. "shell")
```

## Neovim save prompt on close

Installed automatically while the plugin is enabled. Super+W requests Neovim's `:confirm qall`: Yes saves, No discards changes, and Cancel keeps editing. It requires Neovim's default server socket, `hyprctl`, and `notify-send`.

The integration wraps the existing Lua Super+W action and calls it unchanged for other windows. On disable/removal it restores the original callback, provided that callback has not since been replaced. It does not modify Neovim configuration.

Save-on-close is best-effort: if the existing binding format or Lua registry API is unsupported, omanb leaves Super+W unchanged and still installs available open/new shortcuts. If a window API or helper-launch call fails inside the wrapper, it falls back to the original close action. In that fallback mode, the extra Neovim save prompt is unavailable and normal terminal-close behavior applies. Once the helper has launched, an unreachable Neovim still leaves the window open and produces a notification.

Every terminal launched by omanb has a unique `org.omarchy.omanb.s<token>` app ID; the fixed `s` prefix keeps it valid for terminals such as Ghostty even when the random token starts with a digit. The helper checks that window and only contacts Neovim processes carrying the matching `OMANB_SESSION_TOKEN`. This also isolates windows when a terminal uses one shared process. An ordinary Neovim session launched elsewhere is unaffected. If it cannot reach the matching editor, it leaves the window open and notifies you. Other editors keep normal window-close behavior; the save prompt is Neovim-specific.

After manually editing custom bindings, run `hyprctl reload` and `hyprctl configerrors`. To undo those edits, remove your added bindings and restore any previous ones. No manual Super+W binding is needed.
