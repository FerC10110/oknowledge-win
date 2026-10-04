import QtQuick
import qs.Commons
import qs.Ui
import "I18n.js" as I18n

// Bar entry point for oknowledge: an icon, plus a count while links are being
// saved or are left unfinished. The state lives in Service.qml (one instance);
// this widget exists once per monitor and only shows it.
//   left click    open the panel
//   middle click  save what is in the clipboard, opening nothing
//   right click   open the library in the browser
BarWidget {
  id: root
  moduleName: "io.github.ferc10110.oknowledge"

  // Looked up on a timer rather than bound: the service is created
  // asynchronously and can be rebuilt on a plugin reload.
  property var service: null

  readonly property var panel: panelLoader.item
  readonly property bool opened: panel ? panel.opened === true : false
  readonly property bool popoutSwitchClosing: panel ? panel.popoutSwitchClosing === true : false

  readonly property string language: service ? service.language : "en"
  function t(s, args) { return I18n.t(s, root.language, args) }
  readonly property var face: service ? service.face : ({ tone: "normal", text: "", tooltip: { text: "oknowledge", args: [] } })
  readonly property string icon: "\u{F0E15}"        // nf-md-bookmark_multiple

  function open() { if (panel) panel.open() }
  function close() { if (panel) panel.close() }
  function togglePanel() { if (panel) panel.toggle() }
  function closeForPopoutSwitch() { if (panel) panel.closeForPopoutSwitch() }

  function lookupService() {
    var found = bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
    if (found !== service) service = found
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("service" in target) target.service = root.service
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: { lookupService(); injectPanel() }
  onSettingsChanged: injectPanel()
  onServiceChanged: injectPanel()

  Timer {
    interval: 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.lookupService()
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.face.text !== "" && !root.vertical ? root.icon + " " + root.face.text : root.icon
    // The count is more than one glyph: grow the slot to the painted text in a
    // horizontal bar.
    slotSize: vertical ? Style.bar.statusSlot
                        : Math.max(Style.bar.statusSlot, glyphPaintedWidth + Style.space(8))
    active: root.face.tone === "urgent" || root.face.tone === "accent"
    activeColor: root.face.tone === "urgent" ? (root.bar ? root.bar.urgent : Color.urgent) : Color.accent
    tooltipText: root.t(root.face.tooltip.text, root.face.tooltip.args)
    onPressed: function(b) {
      if (b === Qt.RightButton) { if (root.service) root.service.openLibrary() }
      else if (b === Qt.MiddleButton) { if (root.service) root.service.saveClipboard() }
      else root.togglePanel()
    }
  }
}
