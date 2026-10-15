# Rediseño, entrega 2: lo que quedó para después

**Fecha:** 2026-10-14 · **Entrega:** Ocio + Ideas (merge en `main`, aec748c)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 2. Ninguno pierde datos. Los de la entrega 1 que siguen abiertos están
en `2026-10-14-rediseno-biblioteca-pendientes.md`.

## Tests flojos

- Varios tests de JS (`shell.js`, `autosave.js`, `idea.js`) sólo buscan texto
  en el código; las carreras se probaron con Playwright a mano.
- Falta testear: el mapeo de `busy`/`cannot-search` en `FAILURES`; el tope de
  16 links con `back=idea`; `idea-full` con `back=idea`; que ¿Ya existe? se
  habilita con buscador; `/ideas/../x`; que el id de un link o una ficha en
  `/ideas/{id}` dé 404; el escape de `q=<script>` en el catálogo; que Todo
  muestre todas las fichas; `/kind` sobre una idea; el JSON de borrar una
  ficha.

## Código

