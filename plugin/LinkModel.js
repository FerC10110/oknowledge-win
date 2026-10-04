// The logic of the oknowledge widget that needs no QML: what is a link, how to
// call the CLI, and what to tell the user about what came back. node tests it
// (tests/model.test.js); QML ignores the module.exports block at the end.
//
// The prime rule of oknowledge is that a link is never lost, and this file is
// where the widget could break it by words. `oknowledge add` does NOT use its
// exit code as a boolean:
//   0  it worked
//   1  it ran, but the link is unfinished: a partial note, a link another
//      process holds, a retry that left some undone. The link WAS saved.
//   2  the user's input or config is wrong
//   3  something unexpected; the CLI's own message says whether it was queued
// So no text produced here for a nonzero exit says that nothing was saved.
//
// A queue entry's `status` and `error` are independent: `ok` with an `error`
// is a note that was written and had something non-fatal go wrong. Only the
// status says whether it needs attention.
//
// Texts are returned in English; the QML runs them through I18n.t. This file
// cannot import I18n.js (a .js imported from QML cannot import another .js).

// A `pending` entry whose process died stays pending forever. Past this age
// it is shown as unfinished, with Retry, instead of as "in progress" for good.
var STALE_MS = 10 * 60 * 1000
var MAX_URL = 2048
var DEFAULT_PORT = 8787

// ---- links

function looksLikeUrl(text) {
  var s = String(text).trim()
  return s.length <= MAX_URL && /^https?:\/\/\S+$/i.test(s)
}

function clipboardOutcome(text) {
  var s = String(text === null || text === undefined ? "" : text).trim()
  if (s === "") return { kind: "empty", url: "", text: "Nothing in the clipboard" }
  if (!looksLikeUrl(s)) return { kind: "notUrl", url: "", text: "That is not a link" }
  return { kind: "url", url: s, text: "" }
}

// The arguments after the executable. With no mode no flag is passed, so the
// user's `default_content` in config.toml decides full or summary.
function addArgs(url, mode) {
  if (!looksLikeUrl(url)) return null
  var args = ["add", String(url).trim()]
  if (mode === "full") args.push("--full")
  else if (mode === "summary") args.push("--summary")
  args.push("--json")
  return args
}

// Retrying one row is `add` again: for a link whose note is `partial` the CLI
// finishes it, and for one with no note yet it does the whole job. An unknown
// mode gives no flag, so the config's default_content decides.
function retryArgs(row) {
  return addArgs(row.url, row.mode === "full" || row.mode === "summary" ? row.mode : null)
}

// ---- what `add` and `retry` report

function firstLine(text) {
  var lines = String(text || "").split(/\r?\n/)
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, " ").trim()
    if (line !== "") return line
  }
  return ""
}

function parseObject(text) {
  try {
    var value = JSON.parse(text)
    return (value && typeof value === "object" && !Array.isArray(value)) ? value : null
  } catch (e) {
    return null
  }
}

// `retrying` is true for a row's Retry. `add` on a link whose note is not
// `partial` re-analyses nothing (the note may be the user's own) and exits 0;
// after a plain save that is "Already saved", but after a Retry it must not
// read as if the retry worked: the entry stays unfinished and the user should
// know the click changed nothing.
function addOutcome(exitCode, stdout, stderr, retrying) {
  var result = parseObject(stdout)
  var detail = firstLine(stderr)

  if (exitCode === 0) {
    var skipped = result !== null && result.skipped === true
    if (skipped && retrying)
      return { kind: "unchanged", text: "Nothing to redo: the note is already saved",
               detail: "", retry: false }
    return { kind: "saved", text: skipped ? "Already saved" : "Saved", detail: "", retry: false }
  }
  if (exitCode === 1) {
    if (result && result.status === "pending" && !result.path)
      return { kind: "busy", text: "Another process is already saving this link", detail: "", retry: false }
    var why = result && typeof result.error === "string" ? firstLine(result.error) : detail
    if (result && result.status === "failed" && result.path)
      return { kind: "incomplete", text: "The saved note was kept; the new analysis failed",
               detail: why, retry: true }
    return { kind: "incomplete", text: "Saved, but incomplete", detail: why, retry: true }
  }
  if (exitCode === 2)
    return { kind: "error", text: "oknowledge could not run: check the link and your config",
             detail: detail, retry: false }
  if (exitCode === 3)
    return { kind: "error", text: "Something went wrong; the link may be in the queue. Try Retry",
             detail: detail, retry: true }
  return { kind: "error", text: "Could not run oknowledge", detail: detail, retry: false }
}

function clipboardFailure() {
  return { kind: "error", text: "Could not read the clipboard", detail: "", retry: false }
}

// Toast glyphs: md-check only for a save that happened, md-information for a
// click that changed nothing, md-alert for everything else.
function glyphFor(kind) {
  if (kind === "saved") return "\u{F012C}"
  if (kind === "unchanged") return "\u{F02FC}"
  return "\u{F0026}"
}

// omarchy-notification-send reads a known option (--exec, -u ...) in the body
// slot as an option. A CLI error line can say anything, so never let one
// start with a dash.
function notifyBody(text) {
  var s = text === null || text === undefined ? "" : String(text)
  return s.charAt(0) === "-" ? " " + s : s
}

function retryOutcome(exitCode) {
  if (exitCode === 0) return { kind: "saved", text: "Everything is finished", detail: "", retry: false }
  if (exitCode === 1)
    return { kind: "incomplete", text: "Some links are still unfinished", detail: "", retry: true }
  return { kind: "error", text: "Could not run oknowledge", detail: "", retry: false }
}

// `serve` exits 2 with a web.port hint when something already listens on the
// port, which for this CLI means the library is already up.
function serveIsAlreadyUp(exitCode, stderr) {
  return exitCode === 2 && /web\.port/.test(String(stderr || ""))
}

// ---- the queue

function classifyEntry(entry, nowMs) {
  if (entry.status === "ok") return "saved"
  if (entry.status === "pending") {
    var updated = Date.parse(entry.updated)
    return (!isNaN(updated) && nowMs - updated <= STALE_MS) ? "working" : "incomplete"
  }
  return "incomplete"
}

function parseStatus(stdout) {
  try {
    var value = JSON.parse(stdout)
    if (Array.isArray(value)) return { ok: true, entries: value }
  } catch (e) {}
  return { ok: false, entries: [] }
}

var LABELS = { working: "Saving…", saved: "Saved", incomplete: "Incomplete" }

function describeEntry(entry, nowMs) {
  var kind = classifyEntry(entry, nowMs)
  var title = typeof entry.title === "string" ? entry.title.trim() : ""
  return {
    id: entry.id,
    url: entry.url,
    title: title !== "" ? title : String(entry.url),
    kind: kind,
    label: LABELS[kind],
    mode: entry.requested_content,
    retryable: kind === "incomplete",
    // Only an unfinished entry shows its error: on an `ok` one it is a
    // non-fatal note and must not read as a failure.
    detail: kind === "incomplete" && typeof entry.error === "string" ? firstLine(entry.error) : ""
  }
}

// `entries` come newest first, as `oknowledge status --json` prints them.
function summarize(entries, nowMs, limit) {
  var all = entries.map(function (e) { return describeEntry(e, nowMs) })
  var count = function (kind) { return all.filter(function (d) { return d.kind === kind }).length }
  return { working: count("working"), incomplete: count("incomplete"),
           recent: all.slice(0, limit === undefined ? 5 : limit) }
}

// `inflight` is how many `add` runs this widget has started and not seen end:
// the queue file appears a moment after the process starts, and the bar should
// not look idle in between. It is a floor under the queue's own pending count,
// not an addition to it, since a run in flight is also a pending entry.
// `queueReadable` is false when the last `status --json` could not be read, so
// "nothing in the queue" is never said about a queue we could not see.
function queueNote(recentCount, queueReadable) {
  if (queueReadable === false) return "Could not read the queue"
  return recentCount === 0 ? "Nothing in the queue yet" : ""
}

function face(summary, inflight, queueReadable) {
  var working = Math.max(summary.working, inflight || 0)
  if (working > 0)
    return { tone: "accent", text: String(working),
             tooltip: { text: "%1 in progress", args: [working] } }
  if (summary.incomplete > 0)
    return { tone: "urgent", text: String(summary.incomplete),
             tooltip: { text: "%1 unfinished", args: [summary.incomplete] } }
  if (queueReadable === false)
    return { tone: "normal", text: "", tooltip: { text: "Could not read the queue", args: [] } }
  for (var i = 0; i < summary.recent.length; i++)
    if (summary.recent[i].kind === "saved")
      return { tone: "normal", text: "", tooltip: { text: "%1", args: [summary.recent[i].title] } }
  return { tone: "normal", text: "", tooltip: { text: "Nothing in the queue yet", args: [] } }
}

// ---- paths and config, the way the CLI resolves them

function queueDir(env) {
  var base = env.XDG_STATE_HOME
  if (!base || base.charAt(0) !== "/") base = env.HOME + "/.local/state"   // XDG: relative means unset
  return base + "/oknowledge/queue"
}

// web.port from the config's [web] table, which is all of TOML this needs.
function webPort(toml) {
  var lines = String(toml === null || toml === undefined ? "" : toml).split(/\r?\n/)
  var section = ""
  for (var i = 0; i < lines.length; i++) {
    var header = /^\s*\[([^\]]+)\]\s*(#.*)?$/.exec(lines[i])
    if (header) { section = header[1].trim(); continue }
    var m = /^\s*port\s*=\s*(\d+)\s*(#.*)?$/.exec(lines[i])
    if (m && section === "web") {
      var port = Number(m[1])
      return (port >= 1 && port <= 65535) ? port : DEFAULT_PORT
    }
  }
  return DEFAULT_PORT
}

if (typeof module !== "undefined") {
  module.exports = {
    STALE_MS: STALE_MS, looksLikeUrl: looksLikeUrl, clipboardOutcome: clipboardOutcome,
    addArgs: addArgs, retryArgs: retryArgs, clipboardFailure: clipboardFailure,
    glyphFor: glyphFor, notifyBody: notifyBody, queueNote: queueNote, addOutcome: addOutcome, retryOutcome: retryOutcome,
    serveIsAlreadyUp: serveIsAlreadyUp, classifyEntry: classifyEntry, parseStatus: parseStatus,
    summarize: summarize, face: face, queueDir: queueDir, webPort: webPort
  }
}
