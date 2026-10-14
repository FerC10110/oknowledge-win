# Rediseño, entrega 2: Ocio e Ideas

**Fecha:** 2026-10-14 · **Rama:** `feat/rediseno-ocio-ideas`
**Referencia visual:** `design_handoff_oknowledge_redesign/`, sección "Pantallas
dedicadas (versión final)" del README, `Idea detalle.dc.html`, `Ocio.dc.html` y
las capturas `12-ocio.png` y `13-idea.png`. Esa sección **reemplaza** lo que el
README dice de Ocio e Ideas en el panel de detalle. Los números exactos (px,
colores, radios) salen del README.
**Base:** la entrega 1 (`docs/2026-10-14-rediseno-biblioteca-design.md`): tokens,
Geist, barra lateral, campo unificado, toast y estado en la URL valen acá salvo
donde este documento dice otra cosa.

> "arrancá con la entrega 2"
>
> "Rehacé la pantalla de detalle de una Idea según 'Ideas — Idea detalle.dc.html'
> […] Rehacé la pantalla de Ocio según 'Ocio — Ocio.dc.html' […] Sin scroll de
> página […] Todo se autoguarda. Eliminá los botones 'Guardar', los 💾 y los
> formularios de 'Editar etiquetas' […] implementalo por partes: primero Ideas,
> después Ocio."

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Dónde se abre una idea? | En su pantalla propia, `/ideas/{id}` (grid del README: contenido + columna de links) |
| ¿Cómo es la lista `/ideas`? | Barra lateral + tarjetas a todo el ancho, sin panel. Clic abre la pantalla de la idea |
| ¿Cómo se crea una idea? | Con texto en el campo aparece "Nueva idea ↵": crea la idea y abre su pantalla. Enter sigue buscando |
| ¿Título de la idea? | Input sin borde en la cabecera, autoguardado |
| ¿Qué links usa la IA? | Un alcance en la barra "Pedile a la IA": Links vinculados (N) / Toda la biblioteca / Sólo mi texto. Reemplaza las casillas "Usar" y la general |
| ¿Acción "Links que pueden servir" con IA? | Sale de la interfaz (el README dice que el alcance la reemplaza). PUEDEN SERVIR se calcula al instante, sin IA |
| ¿Anime? | Un tipo más en TIPO |
| ¿Favoritos y MARCAS en Ocio? | No, como el diseño final: TIPO y ESTADO. Las estrellas 1–5 hacen ese papel. Las marcas guardadas se conservan en el vault |
| ¿Orden en Ocio? | "Recientes ▾" con Recientes, Título, Año, Tus estrellas, en la URL (`orden=`) |
| ¿Cómo se agrega Ocio desde el campo? | Texto filtra en vivo; "Buscar en catálogos ↵" abre los candidatos en el panel. Prefijo (`película: …`) o link de catálogo guardan directo |
| ¿Orden de trabajo? | Primero Ideas, después Ocio |

## 1. Lo común

**Sin scroll de página.** Las dos pantallas son de alto fijo (`100vh`), como la
Biblioteca; sólo scrollean las columnas internas.

**Barra lateral.** La de la entrega 1 (216px, una sola para toda la app). Los
prototipos dibujan 200px; se mantiene 216 para que la barra no salte al cambiar
de sección. Grupos por sección:

- **Ocio:** TIPO (Todo, Películas, Series, Anime, Libros; un tipo sin fichas no
  se dibuja) y ESTADO (Todo, Por ver, Viendo, Vista; con TIPO = Libros: Por
  leer, Leyendo, Leído). Puntos de estado: Vista `#8fc29a`, Viendo `#a9b4de`,
  Por ver `#6d6f78`.
- **Ideas:** ESTADO (Todo, semilla, en marcha, hecha, descartada). En Todo no
  están las descartadas, como hoy.

**Autoguardado.** No queda ningún botón Guardar, 💾 ni formulario "Editar
etiquetas" en estas pantallas.

- Estado, estrellas, etiquetas (✕ y "+ etiqueta" con Enter), tipo, vínculos:
  se postean al tocarlos. El JS manda `Accept: application/json` y las rutas
  de hoy responden `{"ok": true}` (o `{"ok": false, "error": "…"}` con 4xx/5xx)
  en lugar de redirigir; la pantalla se actualiza sin recargar.
- Textos (título y texto de la idea, TU NOTA de Ocio): se guardan 1 s después
  de la última tecla o al salir del campo. El indicador dice "Guardando…" y
  después "Guardado"; si falla, el toast de error y el texto queda en el campo.
- Sin JavaScript cada formulario tiene su botón Guardar, que el JS esconde, y
  las rutas redirigen como hoy.

**Lo que se va:** `ocio.html`, `ideas.html`, las partes de Ocio e Ideas de
`item.html`, `popup.js`, `/embed/{id}` y `embed.html`, `idea-links.js`,
`idea-link-results.html`, `link-card.html`, `candidates.html` y la página
`/ocio/buscar`, `mine-buttons.html` y `mark-picker.html` si nada más los usa,
`redo.js`. `GET /item/{id}` de una tarjeta redirige a `/ocio?sel={id}` y de
una idea a `/ideas/{id}`, arrastrando `notice`, `n` y `m`.

## 2. Ideas

### Lista `/ideas`

Barra lateral + columna a todo el ancho: campo, cabecera "Ideas · N" (o el
filtro activo) con el selector Lista | Tarjetas, y la lista.

- Parámetros: `estado`, `q`, `vista`, `hasta`. `estado` desconocido = Todo.
- Tarjeta (sin miniatura): título, 3 líneas del texto de la idea (line-clamp),
  "● {estado} · N links". Fila: punto, título, "{estado} · N links", fecha.
- Clic abre `/ideas/{id}`.
- Campo, placeholder "Buscá en tus ideas": texto filtra en vivo (título, texto,
  etiquetas) con `/ideas/lista`. A la derecha aparece **Nueva idea ↵** (botón;
  Enter sigue buscando). Crea la idea con ese texto por el camino de hoy
  (`/ideas/guardar`, la IA le pone título en segundo plano) y abre su pantalla.
- Orden: el de hoy.

### Pantalla `/ideas/{id}`

Grid `216px | 1fr | 400px`, alto fijo. Idea inexistente: 404 de la app.

**Cabecera** (padding `20px 40px 16px`, borde inferior):
- Fila meta: "← Ideas" (vuelve a `/ideas` con el filtro que tenía, guardado en
  `back=`) · "creada 13 oct"; a la derecha el indicador de guardado.
- Fila principal: título editable (input sin borde, 28px/600; vacío no se
  guarda). A la derecha: segmentado de estado, 5 estrellas (clic en la actual
  = 0) y ⋯ con borde: **Regenerar todo con la IA** (lo que hoy hace
  `describe` para una idea: título, resumen, puntos, etiquetas) y **Borrar
  idea** en `#e59a8f`.
- Mientras la IA le pone título a una idea recién creada, el input muestra el
  comienzo del texto atenuado y el sondeo (abajo) lo reemplaza al terminar.
- Etiquetas: chips con ✕ + "+ etiqueta".

**Barra de IA** (padding `12px 40px`, bg `#17181d`, borde inferior):
"PEDILE A LA IA" · **¿Ya existe?** · **Mejorar** · **Ampliar** · "usando" ·
menú de alcance (§2.1). A la derecha, el estado del trabajo en curso
("Buscando…", "Mejoras…", "Ampliación…", `#a9b4de`). Mientras una acción corre,
su botón está deshabilitado. Si no hay motor que pueda buscar en la web,
¿Ya existe? aparece deshabilitado con el motivo de hoy como `title`.

**Cuerpo en 2 columnas** (`1fr | 1.15fr`, borde entre ambas):
- **TU IDEA**: textarea que llena el alto, placeholder "Escribila como te
  salga: la IA la ordena.", nota "se guarda sola".
- **Resultados** en pestañas **Resumen | ¿Ya existe? | Mejoras | Ampliación**:
  - Resumen: el resumen de la idea en párrafo + los puntos numerados `01`…
    (Mono 12px).
  - ¿Ya existe?: el veredicto y cada hallazgo como tarjeta (nombre con link +
    nota), y "Lo tuyo".
  - Mejoras: cada fila `**débil** — arreglo` como tarjeta título + detalle.
  - Ampliación: cada punto como tarjeta.
  - La línea "Con N links: …" de una sección se muestra arriba de sus tarjetas.
  - Pestaña sin contenido: "Todavía no se lo pediste." + botón primario que
    corre esa acción (Resumen: "Regenerar todo con la IA").
  - Al tocar una acción de la barra se abre su pestaña. La pestaña abierta va
    en la URL (`pestana=`); por defecto Resumen.

**Columna "Links de esta idea"** (400px, borde izquierdo):
- Cabecera "Links de esta idea" con contador de vinculados.
- Buscador "Buscá en tus N links para sumar" (en vivo, 250 ms, la búsqueda de
  hoy `/item/{id}/buscar-links`; sin JS, GET con `?q=`).
- **VINCULADOS**: punto de categoría, título (lleva a `/?sel=` del link),
  dominio en Mono, ✕. Un vinculado que ya no está, atenuado con su ✕.
- **PUEDEN SERVIR** (sin búsqueda) o **RESULTADOS** (con búsqueda): borde
  punteado `#2a2b32`, punto, título, dominio, **+ Sumar**. PUEDEN SERVIR = hasta
  6 links con al menos una palabra o etiqueta en común con la idea, rankeados
  con `candidates()` (sin llamar a la IA), sin los vinculados. Ninguno: "Nada
  en común todavía".
- "+ Sumar" y ✕ actualizan la columna y el contador sin recargar. El tope de
  16 vinculados y su aviso no cambian.

### 2.1 Alcance de la IA

`POST /item/{id}/actions/{action}` recibe `alcance`:

| alcance | Qué links lee la IA en Mejorar y Ampliar |
|---|---|
| `vinculados` (por defecto; etiqueta "Links vinculados (N)") | los vinculados que siguen en la biblioteca, en el orden de la idea |
| `todos` ("Toda la biblioteca") | hasta 6 links de toda la biblioteca rankeados con `candidates()` que tengan al menos una palabra en común, vinculados o no |
| `nada` ("Sólo mi texto") | ninguno |

- Valor desconocido = `vinculados`. Vinculados sin ninguno en la biblioteca =
  sin links.
- ¿Ya existe? busca en la web e ignora el alcance.
- El bloque de links del prompt, sus límites y la línea "Con N links: …" no
  cambian (spec de links de ideas, §3). Los campos `with_links`, `use` y
  `category` se van de esta ruta.
- El alcance elegido se recuerda mientras la pantalla está abierta (va en la
  URL, `alcance=`); al entrar es `vinculados`.

### 2.2 Mientras la IA trabaja

`GET /item/{id}/actions/state` → `{"running": [...], "failed": [...],
"title": "…"}`. La pantalla pregunta cada 3 s mientras algo corre (una acción,
o el título de una idea recién creada). Al terminar: recarga las pestañas de
resultados (y el título si cambió), abre la pestaña de esa acción y muestra
el toast "Listo: {sección}" o "Falló: {sección}". Lo que corría se pierde al
reiniciar el servidor, como hoy.

## 3. Ocio

Grid `216px | 1fr | 460px`, alto fijo. Parámetros: `tipo`, `estado`, `q`,
`sel`, `orden`, `hasta`. Desconocidos = Todo / Recientes. `sel` que no está en
la lista abre el primero.

**Centro.**
- Campo: "Buscá en Ocio o pegá un link de IMDb u Open Library".
  Texto filtra en vivo (título, autor, etiquetas) con `/ocio/lista`; a la
  derecha **Buscar en catálogos ↵**. Prefijo de `cards.wanted` o link de
  catálogo: **Guardar ↵** y Enter guarda directo, como hoy.
- Cabecera: "Ocio · N" (o el filtro activo); si hay fichas sin reescribir
  (`engine == ""`), el aviso compacto "• N fichas sin reescribir
  [Reescribir]" (postea a `/ocio/reescribir`, que existe). A la derecha
  "Recientes ▾" con Recientes, Título, Año, Tus estrellas.
- Grilla de pósters (`repeat(auto-fill,minmax(168px,1fr))`, gap 16,
  `aspect-ratio:2/3`, radius 10): la portada (`/cover/{id}`); sin portada, un
  degradé del color del tipo con el título encima. Chip de tipo arriba a la
  izquierda, de estado arriba a la derecha (sin estado, sin chip).
  Seleccionado: borde de 2px `#e7e7ea`. Debajo: título (ellipsis) y "año ·
  ★★★ · {catálogo} {rating}" (cada parte sólo si existe). Sin vista Lista.
- Carga de a 60 y suma al llegar al final, como la Biblioteca.

**Candidatos de catálogos.** "Buscar en catálogos" carga en el panel
`/ocio/candidatos?q=&tipo=` con el tipo del filtro activo (Todo: películas) y
un segmentado de tipo arriba para cambiarlo. Cada candidato: portada chica,
título, año, autor o director, **Guardar** (`/ocio/guardar`, que redirige a
`/ocio?sel=`). Sin resultados: "No encontré nada en los catálogos". Sin JS:
`/ocio?buscar=…&tipo=…` trae los candidatos en el panel.

**Panel derecho** (`/panel/{id}` sirve también para fichas):
- **Barra fija arriba** (padding `16px 24px`, borde inferior): segmentado
  Por ver | Viendo | Vista (libros: Por leer | Leyendo | Leído), 5 estrellas
  (19px, clic en la actual = 0) y ⋯ con **Reescribir la ficha**, **Cambiar
  tipo ▸** (los cuatro tipos; ruta nueva `POST /item/{id}/kind`, cambia `type`
  y `category` como al crearla) y **Borrar**.
- Grid `112px | 1fr`: póster chico y al lado "Tipo · dominio", título
  (24/600), chips de datos (año, duración, `{catálogo} ★ {rating}`) y el botón
  primario **Abrir en {dominio} ↗** (la URL de la ficha, pestaña nueva).
- Si la ficha no está reescrita: "La ficha está como vino de la fuente (en
  inglés)." + **Reescribir en español** (postea a `/item/{id}/describe`).
  Mientras trabaja: "Reescribiendo…", y el panel pregunta cada 3 s a
  `/item/{id}/state` y se recarga al terminar, con toast.
- **DE QUÉ TRATA** (15px/1.6), **TU NOTA** (autoguardada, "se guarda sola" →
  "guardando…" → "guardado"), etiquetas inline.

## 4. Pendientes de la entrega 1 que entran

De `docs/2026-10-14-rediseno-biblioteca-pendientes.md`, porque tocan lo mismo:

- `.chip`, `.chips`, `.warn` de `app.css` limitados a donde se usan.
- Pegar un link que ya tenés lo abre: la redirección `already-saved` lleva `sel`.
- `notice`, `n` y `m` salen de la URL (`replaceState`) una vez mostrado el toast.
- Sin `sel` en la URL, el JS escribe el elegido, así una recarga no mueve el panel.
- La ★ de la tarjeta de la Biblioteca tiene texto accesible.
- Código muerto: lo de §1 "Lo que se va", más `rank_marks`/`used_marks` en
  `page()` y los helpers viejos de `index.py` (`tally`, `years`, `months`,
  `tag_home`, `filter(when=)`) y las reglas de `style.css` que sólo usaban las
  páginas que se van.

## 5. Textos

Claves en inglés y castellano en `i18n.py`, como en la entrega 1. Los del
handoff van tal cual, entre otros: "← Ideas", "creada %1", "Guardando…",
"Guardado", "PEDILE A LA IA", "usando", "Links vinculados (%1)", "Toda la
biblioteca", "Sólo mi texto", "TU IDEA", "Escribila como te salga: la IA la
ordena.", "se guarda sola", "Resumen", "¿Ya existe?", "Mejoras", "Ampliación",
"Todavía no se lo pediste.", "Regenerar todo con la IA", "Borrar idea", "Links
de esta idea", "Buscá en tus %1 links para sumar", "VINCULADOS", "PUEDEN
SERVIR", "RESULTADOS", "+ Sumar", "Nueva idea", "Buscá en Ocio o pegá un link de
IMDb u Open Library", "%1 fichas sin reescribir", "Reescribir",
"Recientes", "Por ver", "Viendo", "Vista", "Por leer", "Leyendo", "Leído",
"Reescribir la ficha", "Cambiar tipo", "Abrir en %1", "La ficha está como vino
de la fuente (en inglés).", "Reescribir en español", "Reescribiendo…", "DE QUÉ
TRATA", "TU NOTA", "Qué te pareció", "Buscar en catálogos".

## 6. Pruebas

- Ideas, lista: filtros de ESTADO (descartadas fuera de Todo), `estado`
  desconocido, búsqueda en vivo, Nueva idea crea y redirige a `/ideas/{id}`.
- Ideas, pantalla: 404; cabecera, barra de IA, pestañas y `pestana=`; MEJORAS
  como tarjetas título + detalle; pestaña vacía con su botón; columna de links
  con VINCULADOS, PUEDEN SERVIR (sin IA, sin vinculados, hasta 6, sólo con
  algo en común) y RESULTADOS con `?q=`.
- Alcance: `vinculados`, `todos` y `nada` arman el prompt con los links
  correctos; desconocido = vinculados; ¿Ya existe? lo ignora; `with_links`,
  `use` y `category` ya no hacen nada.
- `/item/{id}/actions/state` con y sin acción corriendo.
- Cada guardado con `Accept: application/json` (JSON) y sin (redirección), y
  `POST /item/{id}/title` (vacío no guarda).
- Ocio: filtros TIPO y ESTADO, palabras de libros, los cuatro órdenes, el aviso
  de fichas sin reescribir (aparece sólo si hay), `/ocio/candidatos` con stub
  de catálogos (ningún test sale a la red), `POST /item/{id}/kind` (tipo
  desconocido no cambia nada), panel de ficha con y sin reescribir.
- `GET /item/{id}` de ficha e idea redirige; `/embed` da 404; `popup.js`,
  `idea-links.js` y `redo.js` no se sirven.
- Capturas a 1440×900 sobre un vault de prueba, comparadas con `12-ocio.png` y
  `13-idea.png`. El vault real no se toca.

## Fuera de alcance (entregas siguientes)

- Selección múltiple, Deshacer, atajos y su ayuda; Ajustes como modal:
  entrega 3.
- Celular: entrega 4.
- El resto de `docs/2026-10-14-rediseno-biblioteca-pendientes.md`.

Después del merge en `main`, el cambio se lleva a la rama `windows` del fork
como los anteriores.
