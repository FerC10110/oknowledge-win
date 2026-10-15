# Rediseño, entrega 2: lo que quedó para después

**Fecha:** 2026-10-14 · **Entrega:** Ocio + Ideas (merge en `main`, aec748c)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 2. Ninguno pierde datos. Los de la entrega 1 que siguen abiertos están
en `2026-10-14-rediseno-biblioteca-pendientes.md`.

## Tests flojos

- Varios tests de JS (`shell.js`, `autosave.js`, `idea.js`) sólo buscan texto
  en el código; las carreras se probaron con Playwright a mano.
- No prueban nada: `test_web_ocio_rewrite.py:84`,
  `test_web_marks::test_the_picker_is_not_inside_the_popup_link`,
  `test_already_out_there_ignores_the_scope`.
- Falta testear: el mapeo de `busy`/`cannot-search` en `FAILURES`; el tope de
  16 links con `back=idea`; `idea-full` con `back=idea`; que ¿Ya existe? se
  habilita con buscador; `/ideas/../x`; que el id de un link o una ficha en
  `/ideas/{id}` dé 404; el escape de `q=<script>` en el catálogo; que Todo
  muestre todas las fichas; `/kind` sobre una idea; el JSON de borrar una
  ficha.
- El test de `already-saved` de Ocio pasó antes del cambio (no hubo RED).

## Código

- `links_context` vuelve a correr `library.refresh()`.
- `posters.html` vuelve a parsear el año en vez de usar `year_of`.
- CSS muerto: `.mine .field > .failed/.meta`.
- Una línea en blanco de más antes de `GONE` en `app.py`.
