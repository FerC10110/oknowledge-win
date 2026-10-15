# Rediseño, entrega 2: lo que quedó para después

**Fecha:** 2026-10-14 · **Entrega:** Ocio + Ideas (merge en `main`, aec748c)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 2. Ninguno pierde datos. Los de la entrega 1 que siguen abiertos están
en `2026-10-14-rediseno-biblioteca-pendientes.md`.

## Tests flojos

- Lo que corre en node desde la tanda G: las recargas de la lista, la
  búsqueda, las teclas, la capa y las pestañas (`shell.js`); los tiempos, el
  guardado de a uno y la salida (`autosave.js`); el sondeo, su 404 y la URL
  (`idea.js`). Siguen leyendo el código, porque el harness tendría que
  dibujar mucho más DOM: el panel de `shell.js` (esperar los guardados antes
  de cambiar, las ediciones en línea, el borrado desde el panel), el sondeo de
  un link que se analiza, la búsqueda en catálogos de Ocio, los filtros
  gemelos de la barra y la fila de chips; y la búsqueda de links en vivo de
  `idea.js`.
