# Rediseño, entrega 1: lo que quedó para después

**Fecha:** 2026-10-14 · **Entrega:** base + Biblioteca (merge en `main`, b2f25d7)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 1. Ninguno rompe nada. La lista sirve para elegir qué meter en las
entregas 2 (Ocio + Ideas), 3 (modales, teclado, selección múltiple, deshacer)
y 4 (celular).

## Para la entrega 2, porque toca las mismas páginas

- `app.css` cambia el estilo de todas las páginas con sus reglas globales de
  `.chip`, `.chips` y `.warn`, así que los chips de filtro de Ocio, de Ideas y
  de la página de una idea se ven distintos. Hay que limitar esas reglas al
  panel (`.detail .chip`, …).
- `app.css` también pinta todos los links con `a{color:var(--acc)}`, por encima
  de los colores que las páginas viejas ponían a cada elemento.
- `.item` choca con las reglas de `.item` que la página de una nota tiene en
  `style.css`.
- El borde de la pastilla `.warn` de `style.css` se cuela en el aviso del panel.
- Hasta esta entrega, las marcas de Ocio y de las ideas no se listan en ningún
  lado: `/marked` ahora lleva sólo a la Biblioteca.

## Comportamiento

- Pegar un link que ya está guardado no lo abre: falta
  `sel=link_id(clean)` en la redirección `already-saved` de `/add`.
- `notice=`, `n` y `m` quedan en la URL después de que el JS toma el control,
  así que al recargar se repite el aviso.
- Sin `sel` en la URL, cuando la lista se recarga el panel salta al nuevo
  primero (por ejemplo durante un lote). El JS podría escribir
  `items.dataset.current` en la URL.
- Al reprocesar, "Analizando…" no aparece hasta que la tarea toma el lock,
  porque `busy()` ignora el `pending` que escribe la ruta.
- Volver a pegar un link cuya entrada de la cola está en ok o error no lo
  muestra ocupado hasta que el reintento toma el lock.
- Si la descarga falla antes de entrar a la cola, se muestra "Analizando…"
  hasta 120 s.
- Un lock tomado hace más de 6 h deja de figurar en la fila "Analizando…" de
  la lista (`/state` lo sigue viendo).
- `import_links` y los caminos de reintentar y reprocesar no repiten el
  intento del lock, así que un choque con el chequeo puede saltear un link.
- La vista Lista no muestra la marca (★, 📌…), porque vive en la miniatura,
  que en esa vista está oculta.
- El campo "+ etiqueta" no es obligatorio: Enter con el campo vacío postea y
  avisa "guardado".
- Después de un guardado en el panel se pierden el scroll y el foco, así que
  para sumar varias etiquetas hay que volver a clickear.
- Sin JS, por encima de `View.MOST` el link "Ver más" recarga la misma página.
- Una búsqueda hecha sólo de emoji o símbolos ("🔥", "+") cuenta como no buscar.
- La página de error 503 muestra la barra lateral con los contadores en cero.
- Bajo un error del vault, `/lista` devuelve un documento 503 entero.

## shell.js

- Una tanda de "más" que llega tarde puede caer en una lista más nueva.
- El `rootMargin` del IntersectionObserver usa la ventana y no `#list-body`.
- El timer de 250 ms de la búsqueda puede pisar un click en un filtro, y una
  recarga del poller puede caer encima de una búsqueda en curso.
- El `.catch` de `loadList` navega también cuando el pedido ya quedó viejo o
  ante un corte breve de red.
- El poller sigue preguntando por ids que ya no están en pantalla, y un estado
  parcial o desconocido recibe el aviso de "listo".
- La URL puede decir `hasta=72` mientras se ven 120 filas, porque el servidor
  redondea a la tanda. No molesta.
- `FormData(form, submitter)` necesita navegadores de 2023 en adelante.

## Accesibilidad

- La ★ de favorito en las tarjetas es un SVG `aria-hidden` sin texto, así que
  un lector de pantalla no la anuncia (`shelf-items.html`).

## Código muerto y limpieza

- Ya no se usan `redo.js`, `/embed` (sólo lo usan los tests), en `index.py`
  `tally`, `years`, `months`, `tag_home` y `filter(when=)`, los valores por
  defecto del paginador de `page()` y varias reglas de `style.css` del header
  viejo.
- `page()` corre `rank_marks` / `used_marks` en cada pedido, y ninguna
  plantilla lo lee.
- `choose()` copia `library.notes` sólo para contar.
- `return_url` con `back=search|library` arma `/search?…` y parámetros
  `page`/`when` que ya no existen.
- `home.html` repite el markup del aviso de nota ilegible que ya tiene
  `base.html`.
- `.dot` está declarado dos veces en `app.css`.
- El diccionario `fresh` se modifica sin lock. Es seguro por el GIL, pero un
  comentario ayudaría.
- En `app.py`, el import de `library_view` está antes que el de `index`.

## Tests flojos

- El test del tema sólo mira `--bg`, `--fg` y `--accent`.
- Pasan sin probar nada:
  - `test_no_marks_nothing_in_the_nav`.
  - `test_web_cards` con `/search?q=shell`.
  - `test_a_note_with_no_source_asks_for_no_icon`.
  - Las reglas de CSS de picking y meses en `test_web_layout`.
  - `test_the_note_page_shows_the_cover_the_card_showed`, que pasa por la
    redirección a la tarjeta.
- No se testea:
  - El `<title>` y el `.summary` de la página de una nota en Ocio e Ideas.
  - Que agregar una etiqueta repetida no la duplique.
- Los tests de `shell.js` sólo miran el texto del código. Las carreras del
  panel se probaron a mano con Playwright.
