# Rediseño, entrega 2: Ocio e Ideas

**Fecha:** 2026-10-14 · **Rama:** `feat/rediseno-ocio-ideas`
**Referencia visual:** `design_handoff_oknowledge_redesign/` (README §1–§3,
capturas `04` Ocio, `05` Ideas pestaña Idea, `06` Ideas Links vinculados). Los
números exactos (px, colores, radios) salen del README del handoff.
**Base:** la entrega 1 (`docs/2026-10-14-rediseno-biblioteca-design.md`): todo lo
que esa spec fija (tokens, Geist, barra lateral, campo, cabecera de lista,
tarjetas y filas, panel, autoguardado, toast, estado en la URL) vale acá salvo
donde este documento dice otra cosa.

> "arrancá con la entrega 2"

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Anime? | Un tipo más: TIPO = Todo, Películas, Series, Anime, Libros, ★ Favoritos |
| ¿Cómo se agrega Ocio desde el campo? | El texto filtra en vivo; "Buscar en catálogos ↵" abre los candidatos en el panel. Prefijo (`película: …`) o link de catálogo guardan directo, como hoy |
| ¿Cómo se crea una idea? | Con texto en el campo aparece "Nueva idea ↵": crea la idea con ese texto y la abre en el panel. Enter sigue buscando |
| ¿Links de la idea? | Pestaña "Links vinculados (N)": vinculados con "Usar" y ✕, buscador en vivo, PUEDEN SERVIR al instante sin IA. La acción con IA va al ⋯ |
| ¿Título de la idea? | Editable en el lugar: el título del panel es un campo sin borde que se guarda solo |
| ¿Marcas en Ocio e Ideas? | Grupo MARCAS en la barra lateral de cada sección (📌 y las demás en uso), como en la Biblioteca |

## 1. Una sola cáscara para las tres secciones

Ocio e Ideas usan la pantalla de tres columnas de la Biblioteca (`home.html`,
`list.html`, el panel, `shell.js`). Lo que hoy supone "es un link" pasa a
depender de la **sección**, que define:

- placeholder del campo y su botón de la derecha (§4, §5);
- el grupo de filtros de la barra lateral;
- cómo se dibuja un ítem en tarjeta y en fila;
- qué panel abre `/panel/{id}`;
- la palabra de la cabecera ("Ocio · 6", "Ideas · 4", o el filtro activo).

**URLs.**

| Sección | Lista | Fragmento de lista | Parámetros |
|---|---|---|---|
| Biblioteca | `/` | `/lista` | los de la entrega 1 |
| Ocio | `/ocio` | `/ocio/lista` | `tipo`, `mark`, `q`, `sel`, `vista`, `hasta` |
| Ideas | `/ideas` | `/ideas/lista` | `estado`, `mark`, `q`, `sel`, `vista`, `hasta` |

- ★ Favoritos de Ocio es `mark=⭐`, como en la Biblioteca.
- Un `tipo` o `estado` desconocido se ignora (muestra Todo), como hoy.
- `sel` que no está en la lista visible abre el primero; nunca un 500.
- `/panel/{id}` sirve a las tres: elige el panel por el estante donde vive la
  nota (link, tarjeta, idea). 404 si no existe.
- `GET /item/{id}` de una tarjeta o idea redirige a `/ocio?sel={id}` o
  `/ideas?sel={id}`, arrastrando `notice`, `n` y `m`, como ya hacen los links.
  Toda escritura de Ocio e Ideas vuelve por ahí.
- `shell.js` toma la ruta del fragmento de lista de un atributo `data-` de la
  página, en lugar de `/lista` fijo.

**Se va:** `ocio.html`, `ideas.html`, las partes de Ocio e Ideas de `item.html`,
`popup.js`, `/embed/{id}`, `idea-links.js` (su búsqueda en vivo pasa a
`shell.js`), `mine-buttons.html` si nada más lo usa, y el formulario de idea
nueva de `/ideas`. `/ocio/buscar` deja de ser una página propia (§4).

## 2. Autoguardado

Todo se edita en el lugar, sin botón Guardar (handoff, Interactions):

- Estado, estrellas, etiquetas, tipo, marcas y vínculos: formularios
  `data-inline` como los del panel de la Biblioteca. Al tocar, se postea, se
  muestra el toast y se recargan el panel y la lista.
- Textos (TU NOTA de Ocio, texto y título de una idea): se guardan 1 s después
  de la última tecla o al salir del campo, lo que pase primero. A la derecha
  del rótulo: "se guarda sola"; mientras guarda "guardando…"; después
  "guardado". Si falla, el toast de error de la entrega 1 y el texto queda
  como está en el campo. No se recarga el panel al guardar un texto (perdería
  el foco); sí la lista, sin mover la selección.
- Sin JavaScript, cada formulario conserva su botón Guardar; el JS lo esconde.

## 3. Barra lateral

- **Ocio:** grupo **TIPO**: Todo, Películas, Series, Anime, Libros (punto de
  color + nombre + contador; un tipo sin notas no se dibuja), ★ Favoritos.
- **Ideas:** grupo **ESTADO**: Todo, semilla, en marcha, hecha, descartada. En
  Todo no están las descartadas (como hoy); su fila sí cuenta las suyas.
- **Ambas:** grupo **MARCAS** como en la Biblioteca: 📌 Fijados y cada otra
  marca con al menos una nota en esa sección. Sin COLECCIONES.
- El filtro por etiqueta de Ideas sale de la barra; el campo busca por
  etiquetas.

## 4. Ocio

**Lista.**
- Tarjeta: miniatura = la portada (`/cover/{id}`); sin portada, bloque del
  color del tipo. Chip abajo a la izquierda con el catálogo (`source`). ★ si
  es favorita. Subtítulo "{duración} · {estado}" (p. ej. "608 páginas · En
  curso"); sin duración, sólo el estado; sin estado, sólo la duración.
- Fila: punto del tipo, título, el mismo subtítulo, año.
- Orden: el de hoy (guardado, más nuevo primero).

**Campo.** Placeholder "Buscá en Ocio o pegá un link de IMDb / Goodreads".
- Texto común: filtra en vivo por título, autor y etiquetas. A la derecha
  aparece **Buscar en catálogos ↵** (botón, no Enter).
- Ese botón abre en el panel los candidatos de los catálogos para ese texto,
  con el tipo del filtro activo (en Todo o Favoritos: películas), con un
  segmentado de tipo arriba para cambiarlo. Cada candidato: portada chica,
  título, año, autor o director, y **Guardar**. Guardar crea la tarjeta y la
  abre (`/ocio?sel=`). Sin resultados: "No encontré nada en los catálogos".
  Sin JavaScript, el botón hace GET a `/ocio?buscar=…&tipo=…` y la página
  trae los candidatos en el panel.
- Prefijo (`película: …`, los de `cards.wanted`) o link de un catálogo:
  aparece **Guardar ↵** y Enter guarda directo, como hoy en la Biblioteca.

**Panel.**
- Fila meta: chip "● Libros ▾" que abre el menú de tipos y lo cambia en el
  lugar (**ruta nueva**: `POST /item/{id}/kind`; cambia `type` y `category`
  según el idioma, como al crearla). Después "catálogo · año".
- Título; descripción (`summary`) en párrafos.
- Segmentado **Pendiente | En curso | Terminada** y 5 estrellas (clic en la
  actual = 0).
- **TU NOTA**: textarea con autoguardado (§2), placeholder "Qué te pareció".
- Etiquetas con ✕ y "+ etiqueta".
- Barra de acciones: **Abrir original ↵** (la URL del catálogo) · ★ · ⋯ con
  "Reescribir la descripción con IA", las marcas y **Borrar**.
- Mientras se reescribe la descripción: la descripción muestra el esqueleto
  de la entrega 1 y el panel se recarga al terminar, con toast.

## 5. Ideas

**Lista.**
- Tarjeta sin miniatura: título, 3 líneas del texto de la idea (line-clamp),
  y "● {estado} · N links".
- Fila: punto del estado, título, "{estado} · N links", fecha.
- Orden: el de hoy.

**Campo.** Placeholder "Buscá en tus ideas".
- Texto: filtra en vivo por título, texto y etiquetas. A la derecha aparece
  **Nueva idea ↵** (botón; Enter sigue buscando).
- Nueva idea crea la idea con ese texto (el mismo camino que hoy
  `/ideas/guardar`), la IA le pone título en segundo plano, y se abre en el
  panel (`/ideas?sel=`). Mientras no tiene título, el panel y la tarjeta
  muestran el comienzo del texto y la tarjeta está "Analizando…" con el
  sondeo de §5 "Mientras la IA trabaja".

**Panel.**
- Fila meta: chip "● en marcha ▾" que cambia el estado en el lugar; la fecha.
- Título editable en el lugar (§2): campo sin borde con el estilo del título
  (26px/600). Vacío no se guarda.
- Pestañas **Idea | Links vinculados (N)**, subrayado activo de 2px. La pestaña
  abierta va en la URL (`pestana=links`) para que recargar la deje igual; por
  defecto Idea.

**Pestaña Idea.**
- El texto de la idea: textarea sin borde, autoguardado.
- Segmentado de estado (semilla / en marcha / hecha / descartada).
- Lo que escribió la IA, en este orden y sólo las que existen: **YA EXISTE**,
  **MEJORAS** (cada fila `**débil** — arreglo` se dibuja con el título en
  negrita), **AMPLIACIÓN** (lista). La línea "Con N links: …" se conserva.
- Si no hay ninguna: recuadro "Todavía no le pediste nada a la IA. Probá
  Mejorar…".
- Etiquetas con ✕ y "+ etiqueta".

**Pestaña Links vinculados.**
- Los vinculados: punto de categoría, título (abre el link en la Biblioteca,
  `/?sel=`), casilla **Usar** y ✕. Arriba la casilla general "Usar los links
  vinculados" (sólo si hay alguno en la biblioteca). Mismo comportamiento que
  hoy: todas marcadas al abrir; sin la general no se usa ninguno. Un vinculado
  que ya no está se ve atenuado con su ✕.
- El buscador en vivo de hoy (`/item/{id}/buscar-links`), con "+ Sumar" en cada
  resultado.
- **PUEDEN SERVIR**: hasta 6 links de la biblioteca rankeados por palabras y
  etiquetas en común con la idea (el ranking local que ya usa la acción de
  links, sin llamar a la IA), sin los ya vinculados, con borde punteado y
  "+ Sumar". Si la acción con IA ya escribió su sección, esas sugerencias van
  primero, con su "por qué" en una línea.
- El tope de 16 vinculados y su aviso no cambian.

**Acciones.** **¿Ya existe?** · **Mejorar** · **Ampliar** (estas dos con la
selección de "Usar") · ⋯ con "Buscar links con IA" (la acción `links`),
"Completar con IA" (lo que hoy hace `describe` para una idea) y **Borrar**.
Las ideas no muestran estrellas ni ★ (los datos se conservan).
Si no hay motor que pueda buscar en la web, **¿Ya existe?** aparece
deshabilitado con el motivo de hoy como `title`.

**Mientras la IA trabaja.** El botón de la acción en curso dice "pensando…" y
está deshabilitado. El panel pregunta cada 3 s a una ruta nueva,
`GET /item/{id}/actions/state` → `{"running": [...], "failed": [...]}`. Al
terminar una acción se recarga el panel (si la idea sigue siendo la elegida,
como en la entrega 1) y aparece el toast "Listo: {sección}" o "Falló:
{sección}". Al reiniciar el servidor se pierde lo que estaba corriendo, como
hoy.

## 6. Pendientes de la entrega 1 que entran

De `docs/2026-10-14-rediseno-biblioteca-pendientes.md`, porque tocan lo mismo:

- `.chip`, `.chips`, `.warn` de `app.css` limitados al panel y la barra lateral.
- Pegar un link que ya tenés lo abre: la redirección `already-saved` lleva
  `sel`.
- `notice`, `n` y `m` salen de la URL (`replaceState`) una vez mostrado el
  toast.
- Sin `sel` en la URL, el JS escribe el elegido, así una recarga no mueve el
  panel.
- La vista Lista muestra la marca (★, 📌…) en las tres secciones.
- La ★ de la tarjeta tiene texto accesible.
- Código muerto: `redo.js`, `/embed`, `popup.js`, `rank_marks`/`used_marks` en
  `page()`, los helpers viejos de `index.py` (`tally`, `years`, `months`,
  `tag_home`, `filter(when=)`), y las reglas de `style.css` que sólo usaban las
  páginas que se van.

## 7. Textos

Todo texto nuevo entra en inglés como clave y en castellano en `i18n.py`, como
en la entrega 1. Los del handoff van tal cual: "Buscá en Ocio o pegá un link de
IMDb / Goodreads", "Buscá en tus ideas", "TIPO", "ESTADO", "TU NOTA", "se
guarda sola", "Pendiente", "En curso", "Terminada", "Idea", "Links vinculados
(%1)", "PUEDEN SERVIR", "+ Sumar", "MEJORAS", "AMPLIACIÓN", "YA EXISTE",
"Todavía no le pediste nada a la IA. Probá Mejorar…", "¿Ya existe?", "Mejorar",
"Ampliar", "Buscar en catálogos", "Nueva idea".

## 8. Pruebas

- Por sección: cada filtro de la barra devuelve lo que corresponde; `tipo` y
  `estado` desconocidos muestran Todo; `sel` inválido (`../x`, filtrado,
  borrado) abre el primero; `/ocio/lista` e `/ideas/lista` con `desde`.
- Campo: en Ocio, texto común filtra y ofrece catálogos; prefijo o link de
  catálogo guarda; en Ideas, Nueva idea crea y abre. Los catálogos y la IA van
  con stubs: ningún test sale a la red.
- Cada guardado en el lugar, con JavaScript (formulario `data-inline`, toast)
  y sin (botón Guardar, redirección a `?sel=`).
- `POST /item/{id}/kind` cambia tipo y categoría; tipo desconocido no cambia
  nada.
- Panel de idea: pestañas y `pestana=links`; MEJORAS con negrita; el recuadro
  vacío; PUEDEN SERVIR sin llamar a la IA, sin vinculados, hasta 6;
  `/item/{id}/actions/state` con una acción corriendo y sin.
- `GET /item/{id}` de tarjeta e idea redirige con `sel` y el aviso.
- Lo que se borra no deja rutas ni plantillas colgando (`/embed` 404,
  `popup.js` no se sirve).
- Capturas de Ocio, Idea y Links vinculados a 1440×900 sobre un vault de
  prueba, comparadas con `04`, `05` y `06` del handoff. El vault real no se
  toca.

## Fuera de alcance (entregas siguientes)

- Selección múltiple y su barra flotante, Deshacer, atajos `1`/`2`/`3`, `/`,
  `?` y la ayuda: entrega 3.
- Ajustes como modal: entrega 3.
- Celular: entrega 4.
- El resto de `docs/2026-10-14-rediseno-biblioteca-pendientes.md`.

Después del merge en `main`, el cambio se lleva a la rama `windows` del fork
como los anteriores.
