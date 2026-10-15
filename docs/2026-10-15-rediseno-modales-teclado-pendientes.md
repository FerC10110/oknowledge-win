# Rediseño, entrega 3: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** modales, teclado, selección múltiple y
Deshacer (rama `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 3. Ninguno pierde datos: en el peor caso una nota queda en
`oknowledge/trash/` sin Deshacer desde la app, y se recupera desde Obsidian.

## Ajustes

- Un renombre recarga la página al cerrar aunque no haya movido nada. Con dos
  renombres al mismo tiempo y un cierre inmediato, puede no recargar.
- Un guardado que nunca contesta deja esperando los redibujos (sin timeout).
- Si se cierra el modal y se reabre en otra pestaña antes de que conteste el
  primero, puede mostrar la pestaña equivocada.
- Soltar un arrastre de texto sobre el fondo cierra el modal.
- En la página `/settings`, la ✕ navega aunque el último guardado haya
  fallado (el aviso se pierde; antes también se perdía el valor).
- Al reabrir un modal después de Esc, el diálogo mismo toma el foco y muestra
  un borde blanco.

## Código

- Reglas viejas `.sidebar .foot` al lado de las nuevas `.foot-link`; clase
  `bulk-star` sin uso.
- `settings_panel` arma `t`, `lang` y `batch` a mano en vez de usar `page()`.
- `select.js` repite el callback de Deshacer que `app.js` ya hace por defecto.
- `idea.js`: el `refresh(...).then(...)` no atrapa el rechazo (como antes).

## Tests flojos

- Los tests de `settings.js`, `shell.js` (teclas) y `select.js` buscan texto
  en el código; el comportamiento lo probaron scripts de Playwright que no
  están en el repo.
- El harness de `app.js` no cubre textarea/select/contenteditable, Enter sobre
  un link o botón, `?` sin diálogo ni `/`.
- `test_every_translated_string_is_one_the_code_asks_for` compara por
  substring: una traducción sin uso puede sobrevivir si su texto aparece dentro
  de otro.
- El test del foco de Atajos compara el HTML literal.
