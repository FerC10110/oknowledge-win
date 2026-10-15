# Rediseño, entrega 3: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** modales, teclado, selección múltiple y
Deshacer (rama `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 3. Ninguno pierde datos: en el peor caso una nota queda en
`oknowledge/trash/` sin Deshacer desde la app, y se recupera desde Obsidian.

## Código

- `settings_panel` arma `t`, `lang` y `batch` a mano en vez de usar `page()`.

## Tests flojos

- Los tests de `settings.js`, `shell.js` (teclas) y `select.js` buscan texto
  en el código; el comportamiento lo probaron scripts de Playwright que no
  están en el repo.
- El harness de `app.js` no cubre textarea/select/contenteditable, Enter sobre
  un link o botón, `?` sin diálogo ni `/`.
- El test del foco de Atajos compara el HTML literal.
