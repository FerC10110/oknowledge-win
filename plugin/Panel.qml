import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "I18n.js" as I18n

// oknowledge panel: what is in the clipboard (with Full and Summary to save
// it), the last few links and how each one ended up, and the library. It holds
// no state of its own; Service.qml does.
Panel {
  id: okpanel   // not `root`: it is reached from the delegates by id
  moduleName: "io.github.ferc10110.oknowledge"
  ipcTarget: "io.github.ferc10110.oknowledge"
  // The service owns the IPC target (one handler, not one per monitor).
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var service: null

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color accent: (bar && bar.accent !== undefined) ? bar.accent : Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string language: service ? service.language : "en"
  function t(s, args) { return I18n.t(s, language, args) }

  readonly property var clip: service ? service.clip : ({ kind: "empty", url: "", text: "" })

  // Read the clipboard each time the panel opens.
  onOpenedChanged: {
    if (opened && service) {
      service.readClipboard()
      service.refresh()
    }
  }

  function save(mode) {
    if (service) service.saveUrl(clip.url, mode)
    close()
  }

  KeyboardPanel {
    id: panel
    anchorItem: okpanel.anchorItem
    owner: okpanel.hostWidget || okpanel
    bar: okpanel.bar
    open: okpanel.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(Math.max(Style.space(160), layout.implicitHeight), Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: okpanel.close()
      onTabRequested: function(direction) { okpanel.switchPanel(direction) }

      ColumnLayout {
        id: layout
        anchors.fill: parent
        spacing: Style.space(8)

        PanelHero {
          Layout.fillWidth: true
          title: "oknowledge"
          meta: okpanel.t("Paste a link")
          foreground: okpanel.foreground
          fontFamily: okpanel.fontFamily
        }

        // ---- the clipboard
        Text {
          Layout.fillWidth: true
          visible: okpanel.clip.kind !== "url"
          text: okpanel.t(okpanel.clip.text)
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          color: okpanel.dim
          font.family: okpanel.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          Layout.fillWidth: true
          visible: okpanel.clip.kind === "url"
          text: okpanel.clip.url
          textFormat: Text.PlainText
          elide: Text.ElideMiddle
          maximumLineCount: 1
          color: okpanel.foreground
          font.family: okpanel.fontFamily
          font.pixelSize: Style.font.body
        }

        RowLayout {
          Layout.fillWidth: true
          visible: okpanel.clip.kind === "url"
          spacing: Style.space(8)

          Button {
            text: okpanel.t("Full")
            bordered: true
            foreground: okpanel.accent
            fontFamily: okpanel.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: okpanel.save("full")
          }
          Button {
            text: okpanel.t("Summary")
            bordered: true
            foreground: okpanel.foreground
            fontFamily: okpanel.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: okpanel.save("summary")
          }
        }

        // ---- recent links
        Text {
          Layout.fillWidth: true
          text: okpanel.t("Recent")
          textFormat: Text.PlainText
          color: okpanel.foreground
          font.family: okpanel.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }

        Text {
          Layout.fillWidth: true
          visible: !okpanel.service || okpanel.service.recent.length === 0
          text: okpanel.t("Nothing saved yet")
          textFormat: Text.PlainText
          color: okpanel.dim
          font.family: okpanel.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        Repeater {
          model: okpanel.service ? okpanel.service.recent : []
          delegate: ColumnLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: Style.space(2)

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.space(8)

              Text {
                Layout.fillWidth: true
                text: modelData.title
                textFormat: Text.PlainText
                elide: Text.ElideRight
                maximumLineCount: 1
                color: okpanel.foreground
                font.family: okpanel.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              // Words, not only colour, say how it ended up. An entry that is
              // `saved` is never shown as a failure, whatever its `error` says.
              Text {
                text: okpanel.t(modelData.label)
                textFormat: Text.PlainText
                color: modelData.kind === "incomplete" ? okpanel.urgent
                       : modelData.kind === "working" ? okpanel.accent : okpanel.dim
                font.family: okpanel.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              Button {
                visible: modelData.retryable
                text: okpanel.t("Retry")
                bordered: true
                foreground: okpanel.foreground
                fontFamily: okpanel.fontFamily
                fontSize: Style.font.bodySmall
                onClicked: if (okpanel.service) okpanel.service.retryOne(modelData)
              }
            }

            Text {
              Layout.fillWidth: true
              visible: modelData.detail !== ""
              text: modelData.detail
              textFormat: Text.PlainText
              elide: Text.ElideRight
              maximumLineCount: 1
              color: okpanel.dim
              font.family: okpanel.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }
        }

        Button {
          Layout.fillWidth: true
          text: okpanel.t("Open library")
          bordered: true
          foreground: okpanel.foreground
          fontFamily: okpanel.fontFamily
          fontSize: Style.font.bodySmall
          onClicked: { if (okpanel.service) okpanel.service.openLibrary(); okpanel.close() }
        }
      }
    }
  }
}
