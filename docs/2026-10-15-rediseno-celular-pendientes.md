# Rediseño, entrega 4: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** celular (rama `feat/rediseno-celular`,
apilada sobre `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 4. Ninguno pierde datos. El escritorio (≥60rem) no cambió: la
comparación de capturas dio 0 píxeles con diferencia fuerte en todas.

## Tests flojos

- Los tests de la capa (`shell.js`), del modo Seleccionar y de las pestañas
  buscan texto en el código; el comportamiento lo probaron scripts de
  Playwright que no están en el repo.
- Los tests de las pestañas miran sólo las etiquetas en inglés.
- `.drop-title` bajo `pointer: coarse` sólo tiene test de CSS (ninguna
  página lo muestra).
- El back-link de un link analizado se testea contando un texto en
  `app.py`.
