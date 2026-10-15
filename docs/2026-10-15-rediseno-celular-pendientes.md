# Rediseño, entrega 4: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** celular (rama `feat/rediseno-celular`,
apilada sobre `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 4. Ninguno pierde datos. El escritorio (≥60rem) no cambió: la
comparación de capturas dio 0 píxeles con diferencia fuerte en todas.

## Tests flojos

- La capa, el modo Seleccionar y las pestañas corren en node desde la tanda
  G. Siguen leyendo `shell.js`: el borrado desde la capa, los catálogos que
  abren la capa, el ida y vuelta por `a[data-back]`, y los filtros gemelos de
  la barra y la fila de chips (el harness no dibuja la barra lateral).
