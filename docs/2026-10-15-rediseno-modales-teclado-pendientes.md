# Rediseño, entrega 3: lo que quedó para después

**Fecha:** 2026-10-15 · **Entrega:** modales, teclado, selección múltiple y
Deshacer (rama `feat/rediseno-modales-teclado`)

Detalles menores que las revisiones encontraron y que no entraron en la
entrega 3. Ninguno pierde datos: en el peor caso una nota queda en
`oknowledge/trash/` sin Deshacer desde la app, y se recupera desde Obsidian.

## Deshacer y papelera

- Si al restaurar falla el borrado de la copia en `trash/` (después de haber
  vuelto la nota a su lugar), Deshacer la cuenta como "no restaurada" y no
  reconstruye ese estante. La nota sí volvió, y la copia queda en `trash/`.
- Un error inesperado a mitad de un Deshacer corta la vuelta: el resto del lote
  queda en `trash/` y no se reconstruyen los estantes que ya volvieron.
- Un lote con fecha futura (el reloj volvió atrás) nunca se purga.
- Si una carpeta del vault es un symlink colgado, la nota podría volver con
  otro nombre (el chequeo de symlink mira la ruta ya resuelta).
- Con los índices sin reconstruir, el aviso de Deshacer dice "índices
  desactualizados" y no menciona las notas que no volvieron (el JSON sí las
  lista).
- Falta testear: el fallback sin hard links cuando otro gana el nombre, dos
  Deshacer exactamente al mismo tiempo, y el Deshacer con índices viejos.

## Acciones en lote

- Cambiar el estado en lote mira el estado válido nota por nota: en un lote
  mezclado de ideas y fichas, las fichas fallan y las ideas cambian. El aviso
  usa siempre las palabras de Ideas.
- `held_by()` corre dos veces por nota en el estado en lote y en borrar (más
  lecturas del estante de las necesarias).
- Mover en lote la nota abierta fuera de la lista pide dos veces el panel.
- Una casilla marcada con `x` mientras viaja una acción en lote se pierde al
  volver la respuesta.
- "No se seleccionó nada" reusa el texto de las colecciones ("No cards were
  selected…"); la barra nunca lo manda vacío.

## Ajustes

- Las casillas de los motores son las nativas del navegador (azules), no las
  del diseño.
- Sin JS, el campo de archivo de Importar mide 1 px: no se ve qué archivo se
  eligió.
- La pestaña Categorías perdió el autocompletado al unir y el link de cada
  categoría a su lista.
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
- La pista del idioma de la interfaz quedó en dos renglones.

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
- No hay test de que el estado y la marca en lote no reconstruyan índices, ni
  de nota ocupada en tipo/estado/marca en lote.
- `test_every_translated_string_is_one_the_code_asks_for` compara por
  substring: una traducción sin uso puede sobrevivir si su texto aparece dentro
  de otro.
- El test del foco de Atajos compara el HTML literal.
