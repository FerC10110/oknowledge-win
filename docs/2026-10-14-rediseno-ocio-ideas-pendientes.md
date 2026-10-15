# Rediseño, entrega 2: lo que quedó para después

**Fecha:** 2026-10-14 · **Entrega:** Ocio + Ideas (merge en `main`, aec748c)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 2. Ninguno pierde datos. Los de la entrega 1 que siguen abiertos están
en `2026-10-14-rediseno-biblioteca-pendientes.md`.

## Ocio

- Cambiar el orden mientras se busca vacía el campo pero deja `q` en la URL.
- Un click en ESTADO menos de ~100 ms después de uno en TIPO usa los links
  viejos y pierde el `tipo` (gana la última lista, y la barra la acompaña).
- La barra lateral mide 216 px (la spec) y en el diseño ~200 px.

## Panel y autoguardado

- Un guardado de la nota que nunca contesta bloquea los cambios de panel: no
  hay timeout.
- Cuando termina una reescritura, el panel se recarga y el cursor de la nota
  queda al final.
- Con un guardado lento, el resaltado se mueve antes que el panel. Después de
  un guardado fallido, cada click reintenta y vuelve a avisar.
- Un cambio de pestaña con más de 64 KB pendientes muestra un error falso
  (límite de `keepalive`). Un `leave()` fallido se reintenta sólo con la
  próxima tecla.
- Una respuesta de `/actions/state` más lenta que 3 s se descarta por vieja;
  un servidor muy lento podría no llegar a mostrar "Listo".

## Ideas

- Las ideas que llegan con "más" vuelven a `/ideas` sin `hasta`: al volver se
  pierde la profundidad del scroll.
- Los campos ocultos `estado`/`vista` de `/ideas` quedan viejos después de
  navegar con JS.
- "+ etiqueta" pierde el foco después de Enter. El título que propone la IA
  espera mientras el campo de título vacío tiene el foco.

## Biblioteca

- Un link de orden fuera de la barra lateral borra el resaltado de la barra
  (ya pasaba antes de esta entrega).

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
