import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Item {
  id: root
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("shortcuts.py").toString().replace(/^file:\/\//, ""))
  readonly property string token: "omanb-" + Date.now() + "-" + Math.random()
  property bool pending: false

  function install() {
    if (installer.running) pending = true
    else installer.running = true
  }

  Component.onCompleted: install()
  // Inline cleanup still works if the plugin directory has already been removed.
  // The cancellation marker also stops an in-flight installer from adding binds.
  Component.onDestruction: Quickshell.execDetached(["hyprctl", "eval",
    "local token = " + JSON.stringify(token) + "; " +
    "_G.omanb_shortcut_cancellations = _G.omanb_shortcut_cancellations or {}; " +
    "_G.omanb_shortcut_cancellations[token] = true; " +
    "if _G.omanb_release_shortcuts then _G.omanb_release_shortcuts(token) end"])

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event.name === "configreloaded") root.install()
    }
  }

  Process {
    id: installer
    command: ["python3", root.helper, root.token]
    stderr: StdioCollector {
      onStreamFinished: if (text.trim()) console.warn(text.trim())
    }
    onExited: {
      if (root.pending) {
        root.pending = false
        Qt.callLater(root.install)
      }
    }
  }
}
