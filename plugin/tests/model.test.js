// Run with: node --test tests/
const test = require("node:test")
const assert = require("node:assert/strict")
const M = require("../LinkModel.js")
const I18n = require("../I18n.js")

const NOW = Date.parse("2026-10-04T12:00:00.000Z")
const ago = (ms) => new Date(NOW - ms).toISOString()
const entry = (o) => Object.assign({ id: "a", url: "https://x.test/a", requested_content: "full",
  status: "ok", updated: ago(1000), title: null, error: null }, o)

// ---- what counts as a link

test("an http or https URL is a link, with surrounding whitespace ignored", () => {
  assert.equal(M.looksLikeUrl("https://omarchy.org/"), true)
  assert.equal(M.looksLikeUrl("  http://example.com/a?b=1#c\n"), true)
  assert.equal(M.looksLikeUrl("HTTPS://EXAMPLE.COM"), true)
})

test("anything else is not a link", () => {
  for (const bad of ["", "   ", "hello", "ftp://x.test/a", "https://", "javascript:alert(1)",
                     "-h", "--reprocess", "https://a.test two words",
                     "https://a.test/\nhttps://b.test/", null, undefined])
    assert.equal(M.looksLikeUrl(bad), false, JSON.stringify(bad))
})

test("an absurdly long clipboard is not a link", () => {
  assert.equal(M.looksLikeUrl("https://a.test/" + "x".repeat(5000)), false)
})

test("the clipboard says empty, not a link, or the link", () => {
  assert.deepEqual(M.clipboardOutcome(""), { kind: "empty", url: "", text: "Nothing in the clipboard" })
  assert.deepEqual(M.clipboardOutcome(" \n"), { kind: "empty", url: "", text: "Nothing in the clipboard" })
  assert.deepEqual(M.clipboardOutcome("some words"), { kind: "notUrl", url: "", text: "That is not a link" })
  assert.deepEqual(M.clipboardOutcome(" https://omarchy.org/\n"),
                   { kind: "url", url: "https://omarchy.org/", text: "" })
})

// ---- the command line for a save

test("with no mode, no flag is passed: the user's config decides full or summary", () => {
  assert.deepEqual(M.addArgs("https://a.test/", null), ["add", "https://a.test/", "--json"])
  assert.deepEqual(M.addArgs("https://a.test/", undefined), ["add", "https://a.test/", "--json"])
})

test("an explicit mode is passed as its flag", () => {
  assert.deepEqual(M.addArgs("https://a.test/", "full"), ["add", "https://a.test/", "--full", "--json"])
  assert.deepEqual(M.addArgs("https://a.test/", "summary"), ["add", "https://a.test/", "--summary", "--json"])
})

test("the URL is trimmed, and a non-link produces no command at all", () => {
  assert.deepEqual(M.addArgs("  https://a.test/ \n", "full"), ["add", "https://a.test/", "--full", "--json"])
  assert.equal(M.addArgs("--reprocess", "full"), null)
})

// ---- the outcome of `oknowledge add`, by exit code

const addResult = (o) => JSON.stringify(Object.assign({ id: "a", url: "https://x.test/a",
  path: "/v/oknowledge/a.md", status: "ok", engine: "fake", error: null, skipped: false, warnings: [] }, o))

test("exit 0 is saved", () => {
  const o = M.addOutcome(0, addResult({}), "")
  assert.equal(o.kind, "saved")
  assert.equal(o.text, "Saved")
})

test("exit 0 on a link already in the vault says so, and is still a success", () => {
  const o = M.addOutcome(0, addResult({ skipped: true }), "")
  assert.equal(o.kind, "saved")
  assert.equal(o.text, "Already saved")
})

test("exit 0 with unreadable stdout is still saved", () => {
  assert.equal(M.addOutcome(0, "", "").kind, "saved")
  assert.equal(M.addOutcome(0, "not json", "").kind, "saved")
})

test("exit 1 with a partial note means the link WAS saved, incomplete", () => {
  const o = M.addOutcome(1, addResult({ status: "partial", error: "extractor timed out" }), "saved incomplete (...)")
  assert.equal(o.kind, "incomplete")
  assert.equal(o.text, "Saved, but incomplete")
  assert.equal(o.retry, true)
})

test("exit 1 with a refused re-analysis says the saved note was kept", () => {
  const o = M.addOutcome(1, addResult({ status: "failed", error: "boom" }), "")
  assert.equal(o.kind, "incomplete")
  assert.equal(o.text, "The saved note was kept; the new analysis failed")
})

test("exit 1 on a link another process holds says it is being saved", () => {
  const o = M.addOutcome(1, addResult({ status: "pending", path: null }), "another process ...")
  assert.equal(o.kind, "busy")
  assert.equal(o.text, "Another process is already saving this link")
})

test("exit 1 with no readable result is still 'saved, incomplete'", () => {
  const o = M.addOutcome(1, "", "")
  assert.equal(o.kind, "incomplete")
  assert.equal(o.text, "Saved, but incomplete")
})

test("exit 2 is a problem with the link or the config, with the first stderr line as detail", () => {
  const o = M.addOutcome(2, "", "oknowledge: no config file at /h/c.toml\n\nCreate it with")
  assert.equal(o.kind, "error")
  assert.equal(o.text, "oknowledge could not run: check the link and your config")
  assert.equal(o.detail, "oknowledge: no config file at /h/c.toml")
})

test("exit 3 says the link may be in the queue and offers Retry", () => {
  const o = M.addOutcome(3, "", "oknowledge: disk full (the link is in the queue: `oknowledge retry`)")
  assert.equal(o.kind, "error")
  assert.equal(o.text, "Something went wrong; the link may be in the queue. Try Retry")
  assert.equal(o.retry, true)
})

test("an exit code that is not part of the scheme (a crash, a missing binary) is reported as such", () => {
  for (const code of [null, undefined, 127, 137, -1]) {
    const o = M.addOutcome(code, "", "")
    assert.equal(o.kind, "error", String(code))
    assert.equal(o.text, "Could not run oknowledge")
  }
})

test("a nonzero exit never tells the user that nothing was saved", () => {
  const forbidden = /nothing|not saved|couldn'?t save|could not save|failed to save|wasn'?t saved|unsaved|lost/i
  const stdouts = ["", addResult({ status: "partial" }), addResult({ status: "failed" }),
                   addResult({ status: "pending", path: null })]
  for (const code of [1, 2, 3, 4, 127, null])
    for (const out of stdouts) {
      const o = M.addOutcome(code, out, "oknowledge: whatever")
      assert.doesNotMatch(o.text, forbidden, code + " " + out)
      assert.notEqual(o.kind, "saved", code + " " + out)
    }
})

test("the detail is one line of plain text, with control characters removed", () => {
  const o = M.addOutcome(2, "", "oknowledge: bad\u001b[31m thing\r\nsecond line")
  assert.equal(o.detail, "oknowledge: bad [31m thing")
})

test("the detail skips leading blank lines of stderr", () => {
  assert.equal(M.addOutcome(2, "", "\n  \nthe real message\nmore").detail, "the real message")
})

test("retry: 0 finished, 1 some left, anything else could not run", () => {
  assert.equal(M.retryOutcome(0).kind, "saved")
  assert.equal(M.retryOutcome(0).text, "Everything is finished")
  assert.equal(M.retryOutcome(1).kind, "incomplete")
  assert.equal(M.retryOutcome(1).text, "Some links are still unfinished")
  assert.equal(M.retryOutcome(2).kind, "error")
  assert.equal(M.retryOutcome(null).text, "Could not run oknowledge")
})

// ---- the queue

test("an ok entry is saved, even when it carries an error", () => {
  assert.equal(M.classifyEntry(entry({ status: "ok", error: "re-analysis refused" }), NOW), "saved")
  assert.equal(M.classifyEntry(entry({ status: "ok" }), NOW), "saved")
})

test("partial and failed entries are incomplete", () => {
  assert.equal(M.classifyEntry(entry({ status: "partial" }), NOW), "incomplete")
  assert.equal(M.classifyEntry(entry({ status: "failed" }), NOW), "incomplete")
  assert.equal(M.classifyEntry(entry({ status: "something odd" }), NOW), "incomplete")
})

test("a recent pending entry is working", () => {
  assert.equal(M.classifyEntry(entry({ status: "pending", updated: ago(5000) }), NOW), "working")
})

test("a pending entry nobody has touched for a long time is incomplete, not working forever", () => {
  const stale = ago(M.STALE_MS + 1000)
  assert.equal(M.classifyEntry(entry({ status: "pending", updated: stale }), NOW), "incomplete")
  assert.equal(M.classifyEntry(entry({ status: "pending", updated: "" }), NOW), "incomplete")
  assert.equal(M.classifyEntry(entry({ status: "pending", updated: "garbage" }), NOW), "incomplete")
})

test("status output must be one JSON array", () => {
  assert.deepEqual(M.parseStatus("[]"), { ok: true, entries: [] })
  assert.equal(M.parseStatus('[{"id":"a"}]').entries.length, 1)
  for (const bad of ["", "   ", "garbage", "{}", "null", '{"entries":[]}', "[1,"])
    assert.equal(M.parseStatus(bad).ok, false, bad)
})

test("summarize counts working and incomplete, and lists the newest five", () => {
  const entries = [
    entry({ id: "1", status: "pending", updated: ago(1000) }),
    entry({ id: "2", status: "partial" }),
    entry({ id: "3", status: "ok", error: "refused" }),
    entry({ id: "4" }), entry({ id: "5" }), entry({ id: "6" }),
  ]
  const s = M.summarize(entries, NOW)
  assert.equal(s.working, 1)
  assert.equal(s.incomplete, 1)
  assert.deepEqual(s.recent.map((r) => r.id), ["1", "2", "3", "4", "5"])
})

test("an ok entry with an error is listed as Saved with no retry and no error text", () => {
  const r = M.summarize([entry({ status: "ok", error: "re-analysis refused", title: "T" })], NOW).recent[0]
  assert.equal(r.kind, "saved")
  assert.equal(r.label, "Saved")
  assert.equal(r.retryable, false)
  assert.equal(r.detail, "")
})

test("an incomplete entry is retryable and shows its error", () => {
  const r = M.summarize([entry({ status: "partial", error: "timed out" })], NOW).recent[0]
  assert.equal(r.kind, "incomplete")
  assert.equal(r.label, "Incomplete")
  assert.equal(r.retryable, true)
  assert.equal(r.detail, "timed out")
})

test("the title is used, or the URL when there is none", () => {
  const [a, b, c] = M.summarize([entry({ title: "A title" }), entry({ title: null }),
                                 entry({ title: "  " })], NOW).recent
  assert.equal(a.title, "A title")
  assert.equal(b.title, "https://x.test/a")
  assert.equal(c.title, "https://x.test/a")
})

test("a pending entry is labelled Saving", () => {
  const r = M.summarize([entry({ status: "pending", updated: ago(10) })], NOW).recent[0]
  assert.equal(r.label, "Saving…")
  assert.equal(r.retryable, false)
})

test("the requested content mode is read from requested_content", () => {
  const r = M.summarize([entry({ requested_content: "summary" })], NOW).recent[0]
  assert.equal(r.mode, "summary")
})

// ---- retrying one link

test("a row's retry is `add` for that link, in the mode it was asked for", () => {
  const rows = M.summarize([entry({ status: "partial", requested_content: "summary" }),
                            entry({ status: "failed", requested_content: "full", url: "https://x.test/b" })], NOW).recent
  assert.deepEqual(M.retryArgs(rows[0]), ["add", "https://x.test/a", "--summary", "--json"])
  assert.deepEqual(M.retryArgs(rows[1]), ["add", "https://x.test/b", "--full", "--json"])
})

test("a row whose mode is unknown retries with no flag, so the config decides", () => {
  const row = M.summarize([entry({ status: "partial", requested_content: "bogus" })], NOW).recent[0]
  assert.deepEqual(M.retryArgs(row), ["add", "https://x.test/a", "--json"])
})

// ---- the bar face

test("idle face: the icon alone and the title of the last saved link", () => {
  const f = M.face(M.summarize([entry({ title: "Last one" })], NOW))
  assert.equal(f.tone, "normal")
  assert.equal(f.text, "")
  assert.deepEqual(f.tooltip, { text: "%1", args: ["Last one"] })
})

test("idle face with nothing saved yet", () => {
  const f = M.face(M.summarize([], NOW))
  assert.equal(f.tooltip.text, "Nothing saved yet")
})

test("working face: accent, with the count", () => {
  const f = M.face(M.summarize([entry({ status: "pending", updated: ago(10) })], NOW))
  assert.equal(f.tone, "accent")
  assert.equal(f.text, "1")
  assert.deepEqual(f.tooltip, { text: "%1 in progress", args: [1] })
})

test("a save still starting counts as working before its queue file exists", () => {
  const f = M.face(M.summarize([], NOW), 1)
  assert.equal(f.tone, "accent")
  assert.equal(f.text, "1")
  assert.deepEqual(f.tooltip, { text: "%1 in progress", args: [1] })
})

test("saves in flight are not added to the queue's own pending count", () => {
  const s = M.summarize([entry({ status: "pending", updated: ago(10) })], NOW)
  assert.equal(M.face(s, 1).text, "1")
  assert.equal(M.face(s, 3).text, "3")
})

test("a save in flight takes the face over from unfinished links", () => {
  const f = M.face(M.summarize([entry({ status: "partial" })], NOW), 1)
  assert.equal(f.tone, "accent")
})

test("unfinished links show on the bar when nothing is working", () => {
  const f = M.face(M.summarize([entry({ status: "partial" }), entry({ status: "failed" })], NOW))
  assert.equal(f.tone, "urgent")
  assert.equal(f.text, "2")
  assert.deepEqual(f.tooltip, { text: "%1 unfinished", args: [2] })
})

test("working takes the face over from unfinished", () => {
  const f = M.face(M.summarize([entry({ status: "partial" }),
                                entry({ status: "pending", updated: ago(10) })], NOW))
  assert.equal(f.tone, "accent")
})

// ---- paths and config

test("the queue folder follows XDG_STATE_HOME like the CLI does", () => {
  assert.equal(M.queueDir({ HOME: "/h" }), "/h/.local/state/oknowledge/queue")
  assert.equal(M.queueDir({ HOME: "/h", XDG_STATE_HOME: "/s" }), "/s/oknowledge/queue")
  assert.equal(M.queueDir({ HOME: "/h", XDG_STATE_HOME: "relative" }), "/h/.local/state/oknowledge/queue")
  assert.equal(M.queueDir({ HOME: "/h", XDG_STATE_HOME: "" }), "/h/.local/state/oknowledge/queue")
})

test("web.port is read from the [web] table, default 8787", () => {
  assert.equal(M.webPort(""), 8787)
  assert.equal(M.webPort('vault = "/v"\n[web]\nport = 9000\nidle_timeout = 5\n'), 9000)
  assert.equal(M.webPort('[web]\n  port=9001 # mine\n'), 9001)
  assert.equal(M.webPort('[ai]\nport = 1234\n[web]\nidle_timeout = 5\n'), 8787)
  assert.equal(M.webPort('port = 1234\n[web]\n'), 8787)
  assert.equal(M.webPort('[web]\nport = "x"\n'), 8787)
  assert.equal(M.webPort('[web]\nport = 70000\n'), 8787)
  assert.equal(M.webPort(null), 8787)
})

test("serve that cannot bind its port means the library is probably already up", () => {
  assert.equal(M.serveIsAlreadyUp(2, "oknowledge: could not listen on 127.0.0.1:8787; change web.port in the config if it is taken"), true)
  assert.equal(M.serveIsAlreadyUp(2, "oknowledge: no config file"), false)
  assert.equal(M.serveIsAlreadyUp(0, "web.port"), false)
  assert.equal(M.serveIsAlreadyUp(3, "web.port"), false)
})

// ---- every English text the model can emit has a Spanish translation

test("every text the model emits is translated to Spanish", () => {
  const texts = new Set()
  const take = (o) => { texts.add(o.text); if (o.tooltip) texts.add(o.tooltip.text) }
  for (const code of [0, 1, 2, 3, null])
    for (const out of ["", addResult({}), addResult({ skipped: true }), addResult({ status: "partial" }),
                       addResult({ status: "failed" }), addResult({ status: "pending", path: null })]) {
      take(M.addOutcome(code, out, ""))
      take(M.retryOutcome(code))
    }
  for (const c of ["", "x", "https://a.test/"]) take(M.clipboardOutcome(c))
  for (const e of [[], [entry({ status: "partial" })], [entry({ status: "pending", updated: ago(1) })], [entry({})]])
    texts.add(M.face(M.summarize(e, NOW)).tooltip.text)   // face.text is a count
  for (const e of [entry({}), entry({ status: "partial" }), entry({ status: "pending", updated: ago(1) })])
    texts.add(M.summarize([e], NOW).recent[0].label)
  texts.delete("")
  texts.delete("%1")   // a title, which is the user's own text
  for (const text of texts)
    assert.ok(Object.prototype.hasOwnProperty.call(I18n.STRINGS.es, text), "no Spanish for: " + text)
})
