// The user-visible text of oknowledge, in English and Spanish. The key is the
// English string, so English costs nothing: a text with no translation comes
// back as it went in. `%1`, `%2`... take the values in `args`.
//
// This is the language of the *interface*, read from the shared
// ~/.config/omarchy/plugin-language.json. It has nothing to do with the
// language the AI writes notes in, which is `[ai] language` in oknowledge's
// own config.
//
// No QML in here, so node can test it; QML ignores the module.exports block.

var STRINGS = {
  es: {
    "Paste a link": "Pegar un link",
    "Nothing in the clipboard": "No hay nada en el portapapeles",
    "That is not a link": "Eso no es un link",
    "That link cannot be retried from here": "Ese link no se puede reintentar desde acá",
    "Full": "Completo",
    "Summary": "Sólo resumen",
    "Saving…": "Guardando…",
    "Saved": "Guardado",
    "Incomplete": "Incompleto",
    "Retry": "Reintentar",
    "Open library": "Abrir la biblioteca",
    "%1 in progress": "%1 en curso",
    "Recent": "Recientes",
    "Nothing in the queue yet": "Todavía no hay nada en la cola",
    "Could not read the queue": "No se pudo leer la cola",
    "Could not read the clipboard": "No se pudo leer el portapapeles",
    "Nothing to redo: the note is already saved": "Nada que rehacer: la nota ya está guardada",
    "%1 unfinished": "%1 sin terminar",
    "Already saved": "Ya estaba guardado",
    "Saved, but incomplete": "Guardado, pero incompleto",
    "The saved note was kept; the new analysis failed":
      "Se conservó la nota guardada; el nuevo análisis falló",
    "Another process is already saving this link": "Otro proceso ya está guardando este link",
    "oknowledge could not run: check the link and your config":
      "oknowledge no pudo ejecutarse: revisá el link y tu configuración",
    "Something went wrong; the link may be in the queue. Try Retry":
      "Algo salió mal; el link puede estar en la cola. Probá Reintentar",
    "Could not run oknowledge": "No se pudo ejecutar oknowledge",
    "Everything is finished": "Todo terminó",
    "Some links are still unfinished": "Algunos links siguen sin terminar"
  }
}

// text: the English string. lang: "en" or "es"; anything else is English.
// args: the values for %1, %2, ... in order.
function t(text, lang, args) {
  var table = STRINGS[lang]
  // hasOwnProperty, not `table[text] || text`: a text like "constructor" would
  // otherwise find Object.prototype.
  var out = (table && Object.prototype.hasOwnProperty.call(table, text)) ? table[text] : text
  // One pass with replace(): a loop would re-scan its own output and
  // substitute a marker that arrived inside an argument.
  return out.replace(/%(\d+)/g, function (match, digits) {
    var n = Number(digits)
    if (n === 0 || !args || n > args.length) return match
    return String(args[n - 1])
  })
}

if (typeof module !== "undefined") {
  module.exports = { STRINGS: STRINGS, t: t }
}
