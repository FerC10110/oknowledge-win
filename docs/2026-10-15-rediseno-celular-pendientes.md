# Rediseño, entrega 4: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** celular (rama `feat/rediseno-celular`,
apilada sobre `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 4. Ninguno pierde datos. El escritorio (≥60rem) no cambió: la
comparación de capturas dio 0 píxeles con diferencia fuerte en todas.

## Para decidir

- El placeholder del campo de Ocio se corta a 390 px ("…de IMDb u Ope").
  Arreglarlo es cambiar las palabras de §15.
- Al tocar, Chromium dibuja un recuadro de color un instante
  (`-webkit-tap-highlight-color`). Sacarlo es una decisión de diseño.

## Selección

- Una selección hecha en el escritorio que sobrevive a achicar la ventana
  no entra en modo Seleccionar: las casillas no se ven y un toque abre la
  capa (la ✕ de la barra la limpia).

## Tamaños y toques

- La ✕ de cada etiqueta del detalle mide 42 px de alto (ya era así).
- La zona de toque `::after` de los botones de chips puede pisar una fila
  de abajo cuando los chips se parten en dos renglones.
- El fondo de las hojas (menús) no frena el scroll de la página al
  arrastrar.
- En Ocio, el orden queda en su propio renglón debajo del aviso.

## Tests flojos

- Los tests de la capa (`shell.js`), del modo Seleccionar y de las pestañas
  buscan texto en el código; el comportamiento lo probaron scripts de
  Playwright que no están en el repo.
- Los tests de las pestañas miran sólo las etiquetas en inglés.
- `.drop-title` bajo `pointer: coarse` sólo tiene test de CSS (ninguna
  página lo muestra).
- El back-link de un link analizado se testea contando un texto en
  `app.py`.
