import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io
import "I18n.js" as I18n
import "LinkModel.js" as Model

// oknowledge service: the single instance behind the bar widget (which exists
// once per monitor). It owns the interface language, the view of the queue, the
// calls to the `oknowledge` CLI and the IPC target. The plugin knows nothing
// about HTML, the AI or the vault: it pastes a link, calls the CLI and watches
// the queue folder. What the CLI's exit codes mean, and what to tell the user
// about them, is in LinkModel.js (tested with node).
Item {
  id: service

  readonly property string pluginId: "io.github.ferc10110.oknowledge"
  readonly property string homeDir: Quickshell.env("HOME")
  readonly property string cli: homeDir + "/.local/share/oknowledge/venv/bin/oknowledge"
  readonly property string queueDir: Model.queueDir({ HOME: homeDir,
                                                      XDG_STATE_HOME: Quickshell.env("XDG_STATE_HOME") })
  readonly property string omarchyConfigDir: (Quickshell.env("XDG_CONFIG_HOME") || homeDir + "/.config") + "/omarchy"

  // The language of the interface, shared by all my plugins. Not the language
  // the AI writes notes in: that is `[ai] language` in oknowledge's config.
  property string language: "en"
  function t(text, args) { return I18n.t(text, service.language, args) }

  property var summary: Model.summarize([], Date.now())
  property int inflight: 0                    // `add` runs started here and not finished
  readonly property var recent: summary.recent
  readonly property var face: Model.face(summary, inflight)
  readonly property int working: Math.max(summary.working, inflight)

  // What the panel shows about the clipboard, read when it opens.
  property var clip: Model.clipboardOutcome("")
  property int webPort: 8787

  // ---- language
  FileView {
    id: languageFile
    path: service.omarchyConfigDir + "/plugin-language.json"
    blockLoading: true
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      var lang = "en"
      try { lang = String(JSON.parse(text()).language) } catch (e) {}
      service.language = (lang === "es") ? "es" : "en"
    }
    onLoadFailed: service.language = "en"
  }

  // ---- the web port, to open a library that is already running
  FileView {
    id: configFile
    path: service.homeDir + "/.config/oknowledge/config.toml"
    blockLoading: true
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: service.webPort = Model.webPort(text())
    onLoadFailed: service.webPort = 8787
  }

  // ---- the queue: one JSON file per link, so a folder watch tells us when
  // something changed, and `status --json` says what.
  FolderListModel {
    id: queueFolder
    folder: "file://" + service.queueDir
    nameFilters: ["*.json"]
    showDirs: false
    onCountChanged: service.refresh()
  }

  // A file changing inside does not change the count, so poll while anything
  // is in progress. The poll also lets a pending entry nobody finishes age
  // into "unfinished" instead of spinning forever.
  Timer {
    interval: 1500
    repeat: true
    running: service.working > 0
    onTriggered: service.refresh()
  }

  property bool refreshAgain: false
  function refresh() {
    if (statusProc.running) { service.refreshAgain = true; return }
    statusProc.running = true
  }

  Process {
    id: statusProc
    command: [service.cli, "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        // Only stdout is the answer. A reply that does not parse leaves what
        // we last knew on screen instead of wiping it.
        var parsed = Model.parseStatus(text)
        if (parsed.ok) service.summary = Model.summarize(parsed.entries, Date.now())
      }
    }
    onExited: {
      if (service.refreshAgain) { service.refreshAgain = false; service.refresh() }
    }
  }

  // ---- saving a link, and retrying. Each call gets its own Process, so two
  // links saved in quick succession both run: a link is never dropped because
  // another one was still in flight.
  Component {
    id: runnerFactory
    // An Item only so that the Process and its Timer have a parent to live in.
    Item {
      id: run
      property string kind: "add"            // add | retry
      property string subject: ""
      property var argv: []
      property int code: -1
      property string out: ""
      property string err: ""
      property bool exitSeen: false
      property bool outDone: false
      property bool errDone: false
      property bool finished: false

      function check() { if (exitSeen && outDone && errDone) finish() }
      function finish() {
        if (finished) return
        finished = true
        service.runFinished(kind, subject, code, out, err)
        run.destroy(1000)
      }

      Process {
        command: run.argv
        running: true
        stdout: StdioCollector {
          waitForEnd: true
          onStreamFinished: { run.out = text; run.outDone = true; run.check() }
        }
        stderr: StdioCollector {
          waitForEnd: true
          onStreamFinished: { run.err = text; run.errDone = true; run.check() }
        }
        // A process that crashed or never started has no meaningful code.
        onExited: function(exitCode, exitStatus) {
          run.code = (exitStatus === 0) ? exitCode : -1
          run.exitSeen = true
          run.check()
          grace.start()
        }
      }
      // The streams normally end first; if one never reports, do not hang.
      Timer { id: grace; interval: 1500; onTriggered: run.finish() }
    }
  }

  function runFinished(kind, subject, code, out, err) {
    var outcome
    if (kind === "add") {
      service.inflight = Math.max(0, service.inflight - 1)
      outcome = Model.addOutcome(code, out, err)
    } else {
      outcome = Model.retryOutcome(code)
    }
    service.announce(outcome, subject)
    service.refresh()
  }

  // Feedback for gestures that open nothing (middle click, the shortcut).
  function announce(outcome, subject) {
    var ok = outcome.kind === "saved"
    var body = outcome.detail !== "" ? outcome.detail : subject
    Quickshell.execDetached(["omarchy-notification-send", "-g", ok ? "\u{F012C}" : "\u{F0026}",
                             "-u", "normal", service.t(outcome.text), body])
  }

  // `mode` is "full", "summary" or null: with null no flag is passed and the
  // user's `default_content` decides.
  function saveUrl(url, mode) {
    var args = Model.addArgs(url, mode)
    if (args === null) {
      var why = Model.clipboardOutcome(url)
      service.announce({ kind: why.kind, text: why.text, detail: "" }, "")
      return false
    }
    service.inflight += 1
    runnerFactory.createObject(service, { kind: "add", subject: String(url).trim(),
                                          argv: [service.cli].concat(args) })
    service.refresh()
    return true
  }

  // One row's Retry: `add` for that link only. The IPC `retry` still retries all.
  function retryOne(row) {
    var args = Model.retryArgs(row)
    if (args === null) return false
    service.inflight += 1
    runnerFactory.createObject(service, { kind: "add", subject: row.url,
                                          argv: [service.cli].concat(args) })
    service.refresh()
    return true
  }

  function retryAll() {
    runnerFactory.createObject(service, { kind: "retry", subject: "",
                                          argv: [service.cli, "retry"] })
  }

  // ---- the clipboard
  property bool saveWhenRead: false
  Process {
    id: clipProc
    command: ["wl-paste", "--no-newline", "--type", "text"]
    // An empty clipboard, or one holding an image, makes wl-paste exit 1 with
    // no output, which reads as empty.
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        service.clip = Model.clipboardOutcome(text)
        if (service.saveWhenRead) {
          service.saveWhenRead = false
          if (service.clip.kind === "url") service.saveUrl(service.clip.url, null)
          else service.announce({ kind: service.clip.kind, text: service.clip.text, detail: "" }, "")
        }
      }
    }
    // wl-paste missing or failing never reports a stream: do not stay silent.
    // (It prints nothing to stdout when it exits nonzero.)
    onExited: function(exitCode) {
      if (exitCode !== 0 && service.saveWhenRead) {
        service.saveWhenRead = false
        service.clip = Model.clipboardOutcome("")
        service.announce({ kind: "empty", text: service.clip.text, detail: "" }, "")
      }
    }
  }

  function readClipboard() { if (!clipProc.running) clipProc.running = true }
  function saveClipboard() { service.saveWhenRead = true; service.readClipboard() }

  // ---- the library
  // `serve --open` shuts itself down when idle and exits 2 when it is already
  // running, in which case it opens nothing: open the page ourselves.
  function libraryUrl() { return "http://127.0.0.1:" + service.webPort + "/" }

  Process {
    id: serveProc
    command: [service.cli, "serve", "--open"]
    stderr: StdioCollector {
      id: serveErr
      waitForEnd: true
    }
    onExited: function(exitCode) {
      if (Model.serveIsAlreadyUp(exitCode, serveErr.text))
        Quickshell.execDetached(["xdg-open", service.libraryUrl()])
    }
  }

  function openLibrary() {
    if (serveProc.running) Quickshell.execDetached(["xdg-open", service.libraryUrl()])
    else serveProc.running = true
  }

  IpcHandler {
    target: service.pluginId

    function save(): string { service.saveClipboard(); return "ok" }
    function saveUrl(url: string): string { return service.saveUrl(url, null) ? "ok" : "not a url" }
    function open(): string { service.openLibrary(); return "ok" }
    function retry(): string { service.retryAll(); return "ok" }
    function status(): string {
      return JSON.stringify({ working: service.working, incomplete: service.summary.incomplete,
                              recent: service.recent })
    }
  }

  Component.onCompleted: service.refresh()
}
