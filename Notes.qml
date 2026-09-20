import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.dmitry-solomadin.omanb"
  manageIpc: false
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("notes.py").toString().replace(/^file:\/\//, ""))
  property var notes: []
  property string notebook: ""
  property string error: ""
  property string actionError: ""
  readonly property string query: search.text.toLowerCase()
  readonly property var selectedNote: filtered[list.currentIndex] || null
  readonly property bool canCreate: notebook !== "" && error === "" && !reader.running && !deleter.running
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var filtered: notes.filter(function(note) {
    return (note.title + " " + note.file + " " + note.preview).toLowerCase().includes(query)
  })

  function refresh() { if (!reader.running && !deleter.running) reader.running = true }
  function deleteSelected() {
    if (!selectedNote || reader.running || deleter.running) return
    actionError = ""
    deleter.command = ["python3", helper, "delete", selectedNote.selector]
    deleter.running = true
  }
  function open() {
    search.text = ""
    list.currentIndex = filtered.length ? 0 : -1
    actionError = ""
    controller.show()
    refresh()
  }
  function launch(action, selector) {
    var args = ["python3", helper, action]
    if (selector) args.push(selector)
    Quickshell.execDetached(args)
    close()
  }
  function editSelected() {
    if (!deleter.running && selectedNote) launch("edit", selectedNote.selector)
  }
  function moveSelection(delta) {
    if (!filtered.length) return
    list.currentIndex = Math.max(0, Math.min(filtered.length - 1, list.currentIndex + delta))
    list.positionViewAtIndex(list.currentIndex, ListView.Contain)
  }

  Component.onCompleted: refresh()
  Process {
    id: deleter
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.actionError = JSON.parse(text).error }
        catch (e) { root.actionError = "Could not delete the note." }
      }
    }
    onExited: function(code, status) {
      if (code !== 0) root.actionError = "Notes helper failed while deleting."
      Qt.callLater(root.refresh)
    }
  }
  Timer { interval: 5000; running: root.opened; repeat: true; onTriggered: root.refresh() }
  Process {
    id: reader
    command: ["python3", root.helper, "list"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var data = JSON.parse(text)
          // Avoid resetting the selection and scroll position on unchanged refreshes.
          if (JSON.stringify(root.notes) !== JSON.stringify(data.notes)) {
            var selector = root.selectedNote ? root.selectedNote.selector : ""
            root.notes = data.notes
            // Keep the same note selected when edits change the sort order.
            list.currentIndex = selector ? root.filtered.findIndex(note => note.selector === selector) : (root.filtered.length ? 0 : -1)
          }
          root.notebook = data.notebook
          root.error = data.error
        } catch (e) { root.error = "Could not read nb notes." }
      }
    }
    onExited: function(code, status) {
      if (code !== 0) root.error = "Notes helper failed. Check that Python and nb are installed."
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰎞"
    tooltipText: "omanb · nb notes\nRight-click: new note"
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) root.launch("new")
      else if (mouseButton === Qt.LeftButton) root.toggle()
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.opened
    focusTarget: search
    contentWidth: fittedContentWidth(Style.space(470))
    contentHeight: fittedContentHeight(contentLayout.implicitHeight)

    ColumnLayout {
      id: contentLayout
      anchors.fill: parent
      spacing: Style.space(12)
      Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape) { root.close(); event.accepted = true }
        else if (event.key === Qt.Key_N && (event.modifiers & Qt.ControlModifier)) {
          if (root.canCreate) root.launch("new", root.notebook)
          event.accepted = true
        }
      }
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(12)
        Controls.TextField {
          id: search
          Layout.fillWidth: true
          placeholderText: "Search notes…"
          color: root.foreground
          placeholderTextColor: Qt.alpha(root.foreground, 0.5)
          selectionColor: Qt.alpha(root.foreground, 0.3)
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          padding: Style.space(10)
          background: Rectangle {
            radius: 0
            color: Qt.alpha(root.foreground, 0.06)
            border.color: Qt.alpha(root.foreground, 0.2)
          }
          onTextChanged: {
            list.currentIndex = root.filtered.length ? 0 : -1
            list.positionViewAtBeginning()
          }
          Keys.onDownPressed: root.moveSelection(1)
          Keys.onUpPressed: root.moveSelection(-1)
          Keys.onDeletePressed: function(event) {
            if (!event.isAutoRepeat) root.deleteSelected()
            event.accepted = true
          }
          onAccepted: root.editSelected()
        }
        Controls.Button {
          id: newButton
          text: "+ New"
          enabled: root.canCreate
          focusPolicy: Qt.NoFocus
          horizontalPadding: Style.space(11)
          Layout.preferredHeight: search.implicitHeight
          contentItem: Text {
            text: newButton.text
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            color: root.foreground
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
          }
          background: Rectangle {
            color: Qt.alpha(root.foreground, newButton.hovered ? 0.16 : 0.07)
            border.color: Qt.alpha(root.foreground, 0.15)
          }
          opacity: enabled ? 1 : 0.45
          onClicked: root.launch("new", root.notebook)
        }
      }
      Text {
        visible: root.actionError !== "" || root.error !== "" || root.filtered.length === 0
        Layout.fillWidth: true
        text: root.actionError || root.error || (reader.running ? "Loading notes…" : root.query ? "No matching notes." : "No notes yet. Create your first note with + New.")
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        color: root.foreground
      }
      ListView {
        id: list
        visible: count > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredHeight: Math.min(Style.space(350), contentHeight)
        clip: true
        spacing: Style.space(6)
        model: root.filtered
        currentIndex: 0
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: Rectangle {
          required property var modelData
          required property int index
          width: list.width
          height: noteContent.implicitHeight + Style.space(20)
          radius: 0
          color: ListView.isCurrentItem || hover.containsMouse ? Qt.alpha(root.foreground, 0.10) : "transparent"
          Column {
            id: noteContent
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: Style.space(10) }
            spacing: Style.space(5)
            Text {
              width: parent.width
              text: modelData.title
              textFormat: Text.PlainText
              elide: Text.ElideRight
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
              color: root.foreground
            }
            Text {
              width: parent.width
              text: modelData.preview || modelData.file
              textFormat: Text.PlainText
              wrapMode: Text.Wrap
              maximumLineCount: 3
              elide: Text.ElideRight
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              color: Qt.alpha(root.foreground, 0.65)
            }
          }
          MouseArea {
            id: hover
            anchors.fill: parent
            hoverEnabled: true
            enabled: !deleter.running
            onClicked: root.launch("edit", modelData.selector)
          }
        }
      }
      Text {
        Layout.fillWidth: true
        text: "↑↓ select · Enter edit · Delete remove · Ctrl+N new · Esc close"
        textFormat: Text.PlainText
        font.family: root.fontFamily
        font.pixelSize: Style.font.body * 0.85
        color: Qt.alpha(root.foreground, 0.55)
        wrapMode: Text.Wrap
      }
    }
  }
}
