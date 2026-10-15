# Rediseño, entrega 3: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** modales, teclado, selección múltiple y
Deshacer (rama `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 3. Ninguno pierde datos: en el peor caso una nota queda en
`oknowledge/trash/` sin Deshacer desde la app, y se recupera desde Obsidian.

## Código

- `settings_panel` arma `t`, `lang` y `batch` a mano en vez de usar `page()`.
  Tanda G lo dejó así a propósito: `page()` refresca los tres estantes y, si
  la biblioteca no se puede leer, devuelve `error.html` entero con 503, que
  dentro del modal sería una página dentro de otra. Si se quiere unificar,
  hace falta un `chrome()` con sólo `t`/`lang`/`batch` que usen los dos.

## Tests flojos

- `select.js`, las teclas de `shell.js` y casi todo `settings.js` corren en
  node desde la tanda G. De `settings.js` siguen leyendo el código el
  selector de modelos, el botón de una acción y que no use `localStorage`.
