// Run with: node --test tests/
const test = require("node:test")
const assert = require("node:assert/strict")
const I18n = require("../I18n.js")

test("English returns the text as it came in", () => {
  assert.equal(I18n.t("Saved", "en"), "Saved")
})

test("a text with no translation comes back in English", () => {
  assert.equal(I18n.t("Not translated yet", "es"), "Not translated yet")
})

test("Spanish returns the translation", () => {
  assert.equal(I18n.t("Saved", "es"), "Guardado")
})

test("an unknown language falls back to English", () => {
  assert.equal(I18n.t("Saved", "de"), "Saved")
  assert.equal(I18n.t("Saved"), "Saved")
})

test("%1 takes its value, and a translation keeps the marker", () => {
  assert.equal(I18n.t("%1 in progress", "en", [3]), "3 in progress")
  assert.equal(I18n.t("%1 in progress", "es", [3]), "3 en curso")
})

test("%0, a missing argument and a lone % are left alone", () => {
  assert.equal(I18n.t("a %0 b", "en", ["x"]), "a %0 b")
  assert.equal(I18n.t("%1 and %2", "en", ["x"]), "x and %2")
  assert.equal(I18n.t("100% sure", "en"), "100% sure")
})

test("a key named like an Object.prototype member is not found there", () => {
  assert.equal(I18n.t("constructor", "es"), "constructor")
})

test("a value that looks like a marker is not substituted twice", () => {
  assert.equal(I18n.t("%1 / %2", "en", ["%2", "b"]), "%2 / b")
})
