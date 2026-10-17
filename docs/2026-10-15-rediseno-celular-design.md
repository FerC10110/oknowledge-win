# Rediseño, entrega 4: el celular

**Fecha:** 2026-10-15 · **Rama:** `feat/rediseno-celular`, apilada sobre
`feat/rediseno-modales-teclado` (entrega 3)
**Referencia visual:** `design_handoff_oknowledge_redesign/README.md`, párrafo
"Responsive (celular…)" de "Interactions & Behavior" y los tokens;
`oknowledge Rediseño.dc.html` → `data-screen-label="1a celular"` (390×844). Los
números exactos (px, colores, radios) salen de ahí. El handoff no dibuja Ocio,
Ideas, el detalle, Ajustes ni la barra de lote en el celular: lo que este
documento dice de esas pantallas sale de aplicar las mismas reglas.
**Base:** entregas 1, 2 y 3 (`2026-10-14-rediseno-biblioteca-design.md`,
`2026-10-14-rediseno-ocio-ideas-design.md`,
`2026-10-14-rediseno-modales-teclado-design.md`). Tokens, campo unificado,
`answer()`, toast, modales, teclado, selección múltiple y Deshacer valen acá
salvo donde este documento dice otra cosa. El escritorio no cambia.

> El usuario está durmiendo y pidió seguir con todo lo pendiente. Ninguna
> decisión de abajo se le consultó: todas van marcadas para que las revise.

## Decisiones tomadas

| Pregunta | Respuesta | Estado |
|---|---|---|
| ¿Dónde empieza "celular"? | Un solo corte de armazón, `max-width: 60rem`: el que hoy ya hace caer las tres columnas "sin pulir" (`app.css:64`). Debajo, una columna. Entre 42rem y 60rem (celular acostado, tablet) la misma columna con más columnas de tarjetas | decidido sin consultar (revisar) |
| ¿Y lo táctil? | Aparte del ancho: `(hover: none)` muestra lo que hoy espera el mouse (checkboxes); `(pointer: coarse)` esconde lo que sólo sirve con teclado (Atajos, hints `1` `2` `3`, `/`, `↵`). Una tablet ancha con dedo sigue en escritorio, pero sin cosas invisibles | decidido sin consultar (revisar) |
| ¿Qué pasa con las 3 columnas? | La barra lateral no se ve. Queda: barra de arriba · columna central · barra de pestañas abajo. El panel de detalle es una capa a pantalla completa que se abre sobre la lista | decidido sin consultar (revisar) |
| ¿Barra de arriba? | Como el handoff: "oknowledge" a la izquierda y "Ajustes" a la derecha (abre el modal; lleva el contador del lote que corre) | decidido sin consultar (revisar) |
| ¿Pestañas de abajo? | Biblioteca · Ocio · Ideas · Favoritos, iguales en toda página. Sin contadores ni hints de tecla | decidido sin consultar (revisar) |
| ¿Qué es "Favoritos"? | Un atajo al filtro de hoy: `/?mark=⭐`, la Biblioteca filtrada por ★. Encendida, "Biblioteca" se apaga. Ocio no tiene Favoritos (entrega 2) y las ideas tampoco, así que no hay una vista mixta | decidido sin consultar (revisar) |
| ¿Dónde van categorías, marcas, colecciones, TIPO, ESTADO? | En una sola fila de chips con scroll horizontal debajo del campo, como el handoff. Los grupos van separados por una raya fina: Biblioteca = Todo + categorías · marcas · colecciones; Ocio = TIPO · ESTADO; Ideas = ESTADO. ★ Favoritos no se repite: es la 4.ª pestaña. Sin cajón lateral | decidido sin consultar (revisar) |
| ¿Contadores en los chips? | No, como el handoff. El número va en el `title` | decidido sin consultar (revisar) |
| ¿"Atajos" en el celular? | No se ve (es del pie de la barra lateral, que no se dibuja, y además `pointer: coarse` lo esconde). Con un teclado físico, `?` lo sigue abriendo | decidido sin consultar (revisar) |
| ¿Cómo se abre el detalle? | **Pantalla completa**, no bottom sheet: el panel ya tiene barra de acciones abajo y cabecera propia en Ocio, y una hoja a medias deja el resumen en 2/3 de pantalla. Arriba lleva "← Biblioteca" (o "← Ocio") | decidido sin consultar (revisar) |
| ¿Cuándo está abierto? | Cuando la URL trae `sel=` (lo elegiste vos, o volviste de guardar un link). Sin `sel`, el servidor elige el primero como hoy, pero en el celular el panel queda cerrado | decidido sin consultar (revisar) |
| ¿Botón atrás del navegador? | Cierra el detalle y deja la lista donde estaba. Tocar una tarjeta hace `pushState` (sólo en el celular); el escritorio sigue con `replaceState` | decidido sin consultar (revisar) |
| ¿Y "← Biblioteca" o Esc? | Hacen lo mismo que atrás si la capa la abrió esta página; si la página arrancó con `sel=` (recarga, link compartido) sacan `sel` con `replaceState` y cierran, sin salir del sitio | decidido sin consultar (revisar) |
| ¿Ocio, "Buscar en catálogos"? | Los candidatos se abren en la misma capa a pantalla completa, con la misma vuelta | decidido sin consultar (revisar) |
| ¿Lista de Ideas? | Sin panel, como en escritorio: tocar abre `/ideas/{id}`. Tarjetas en 1 columna (2 desde 42rem); Lista igual que en Biblioteca | decidido sin consultar (revisar) |
| ¿Pantalla de una idea? | Una columna que scrollea como página: cabecera (título, y debajo estado, estrellas y ⋯), barra de IA con scroll horizontal, TU IDEA, resultados con sus pestañas, y al final "Links de esta idea". Sin pestañas nuevas | decidido sin consultar (revisar) |
| ¿Ajustes en el celular? | El mismo `<dialog>`, a pantalla completa. Pestañas con scroll horizontal; las filas etiqueta/segmentado se apilan. Atrás lo cierra | decidido sin consultar (revisar) |
| ¿Menús (`details.menu`)? | En el celular se abren como hoja desde abajo, a todo el ancho, con fondo `#0009`; tocar el fondo cierra. Así ninguno se sale de la pantalla | decidido sin consultar (revisar) |
| ¿Selección múltiple sin hover? | Botón "Seleccionar" en la cabecera de lista (sólo celular, sólo con JS). Prende un modo con checkbox visible en cada ítem, y tocar el ítem lo marca en vez de abrirlo. "Cancelar" (el mismo botón) o ✕ salen. Sin long-press | decidido sin consultar (revisar) |
| ¿Barra de lote y pestañas? | Mientras se selecciona, la barra de lote ocupa el lugar de las pestañas, a todo el ancho. ★ Favorito queda como ★ sola | decidido sin consultar (revisar) |
| ¿Toast? | Arriba al centro como en escritorio, debajo del notch, con ancho máximo y texto que puede ir en dos líneas. No choca con las pestañas | decidido sin consultar (revisar) |
| ¿Borrar desde el detalle? | En el celular cierra el detalle (vuelve a la lista) y muestra el toast con Deshacer. Deshacer recarga la lista y no abre nada | decidido sin consultar (revisar) |
| ¿Teclado? | No cambia nada: las teclas siguen registradas, sin ayuda visible. En el celular `j`/`k` eligen pero no abren la capa | decidido sin consultar (revisar) |
| ¿Tamaño de letra del campo? | 16px (el handoff dice 15): menos de 16 hace que Safari en iOS acerque la página al enfocar. Vale para todo input del celular | decidido sin consultar (revisar) |
| ¿Alto de la pantalla? | `100dvh` (con `100vh` antes, para quien no lo entiende). La lista scrollea por dentro, como el handoff; barra de arriba, campo, chips y pestañas quedan fijos | decidido sin consultar (revisar) |
| ¿Notch y barra de gestos? | `viewport-fit=cover` en el `<meta viewport>` y `env(safe-area-inset-*)` en barra de arriba, pestañas, detalle, barra de lote, hojas de menú y toast | decidido sin consultar (revisar) |
| ¿Objetivos táctiles? | ≥44×44px en pestañas, "Ajustes", "← volver", botones del detalle, ítems de menú, estrellas, checkbox (zona de toque, no el dibujo), chips (zona de toque) y Lista/Tarjetas | decidido sin consultar (revisar) |
| ¿Lo de `layout.js` para el celular viejo? | Se va: plega `details.filters` y suelta el `autofocus` de `header input[type=search]`, y ninguna de las dos cosas existe después del rediseño. Queda la clase `js` y la limpieza de `notice`/`undo` | decidido sin consultar (revisar) |
| ¿Qué queda sólo para escritorio? | Barra lateral, ayuda de atajos visible, hints de tecla, drag & drop de WhatsApp (en el celular sólo "Elegir archivo"), hover de tarjetas | decidido sin consultar (revisar) |

## 1. Cortes

Tres consultas de medio, cada una por su razón:

| Consulta | Qué cambia |
|---|---|
| `@media (max-width: 60rem)` | el armazón: una columna, barra de arriba, pestañas, detalle como capa, fila de chips, menús como hoja, Ajustes a pantalla completa. Reemplaza el bloque "sin pulir" de `app.css:64` |
| `@media (max-width: 60rem) and (min-width: 42rem)` | sólo grillas: tarjetas de la Biblioteca en 3 columnas, pósters `auto-fill` de 168px, tarjetas de Ideas en 2 |
| `@media (hover: none)` | los checkboxes se ven siempre en escritorio táctil (§9). Ya existe uno en `style.css:255` para `.actions` de las páginas viejas |
| `@media (pointer: coarse)` | esconde "Atajos", `kbd.key`, el `/` del campo y los `↵` de los botones (§4) |

`60rem` es la constante que usan el CSS y el JS (`matchMedia("(max-width:
60rem)")`, una sola vez en `app.js`, expuesta como `oknowledge.phone()`).
Entre 60rem y unos 70rem el escritorio de tres columnas queda apretado; no es
parte de esta entrega (ver Preguntas).

## 2. El armazón

### 2.1 Qué se dibuja

Dos partials nuevos, incluidos por `base.html` **dentro de** `.app` (antes de
la barra lateral uno, al final el otro), así que valen para toda página: las
tres secciones, la pantalla de una idea y las páginas viejas (`/settings`,
`/import`, `/retry`, errores). En escritorio son `display: none` y no ocupan
celda de la grilla.

- `topbar.html`: `<header class="topbar">` con el logo (`<a href="/">`) y
  `<a href="/settings" class="topbar-settings" data-modal="settings">Ajustes</a>`,
  con el mismo contador `3/10` que el pie de la barra lateral.
- `tabbar.html`: `<nav class="tabbar" aria-label="Secciones">` con cuatro
  links: Biblioteca (`/`), Ocio (`/ocio`), Ideas (`/ideas`), Favoritos
  (`/?mark=%E2%AD%90`). El activo lleva `class="on"` y `aria-current="page"`:
  Favoritos cuando la sección es `links` y `view.mark == '⭐'` (sin búsqueda);
  Biblioteca en el resto de la Biblioteca; Ocio e Ideas por `side.section`
  (la pantalla de una idea es Ideas).

### 2.2 Debajo de 60rem

```
.app            flex en columna, height 100dvh (100vh antes), overflow hidden
  .topbar       padding 18px 16px 10px + safe-area-top; logo 16/600, Ajustes 13px #8b8d96
  .sidebar      display: none
  .center       flex: 1; min-height: 0; sin borde derecho
  .detail       cerrado: display none · abierto: capa fija (§6)
  .tabbar       fija abajo
```

- **Pestañas:** `position: fixed; bottom: 0; left: 0; right: 0`, borde superior
  `1px #22232a`, bg `#141519`, grid de 4 columnas iguales, `padding: 8px 8px
  max(8px, env(safe-area-inset-bottom))`. Cada link: 12px, `min-height: 44px`,
  centrado, `#8b8d96`; activo `#e7e7ea` 500. Su alto queda en
  `--tabbar-h: calc(60px + env(safe-area-inset-bottom))`, y `.center` lleva ese
  `padding-bottom` para que la lista no quede debajo.
- **Páginas que scrollean** (pantalla de una idea, páginas viejas): `.app` pasa
  a `height: auto`, scrollea el documento, la barra de arriba se va con el
  scroll y las pestañas siguen fijas; el `<body>` lleva `padding-bottom:
  var(--tabbar-h)`.
- **Ninguna página scrollea de costado:** `.app { overflow-x: clip }` como red,
  pero cada fuente de desborde conocida tiene su regla (§12).

## 3. Filtros: la fila de chips

Partial nuevo `filter-chips.html`, que arma la fila con los mismos datos que la
barra lateral (`groups` y `view` en la Biblioteca; `filters` en Ocio e Ideas):

```html
<nav class="chip-row" aria-label="Filtros">
  <div class="chip-group">…<a href="…" data-nav class="fchip on" title="12">Redes</a>…</div>
  <div class="chip-group" data-apart>…</div>
</nav>
```

- Va en `home.html`, `ocio-shelf.html` e `idea-shelf.html`, entre el campo y
  `#list`. En escritorio `display: none`.
- **Biblioteca:** grupo 1 = Todo + categorías (con su punto de 7px); grupo 2 =
  las marcas en uso (emoji solo; 📌 con "Fijados"); grupo 3 = colecciones. Los
  hrefs son los de la barra lateral (`view.url(cat=…, tag='', mark='', …)`).
  ★ Favoritos no está: es una pestaña. Un grupo vacío no se dibuja.
- **Ocio:** TIPO y ESTADO, cada uno `data-apart` (se eligen por separado, como
  en la barra lateral). **Ideas:** ESTADO.
- **Las fechas, en una fila propia debajo** (2026-10-17, con el grupo FECHAS de
  la barra lateral): un segundo `<nav class="chip-row chip-dates">` con Todo +
  los años, y los meses del año abierto a continuación. Son el otro eje, así
  que cada fila tiene su propio Todo: el de arriba borra el "qué" y deja el
  período; el de abajo borra el período y deja el "qué". `sideFilters()`
  reemplaza **todas** las filas, no la primera, o la de años vieja quedaría
  dibujada debajo de las nuevas; y el chip encendido se trae a la vista en
  cada fila.
- Estilo del handoff: 13px, `padding: 7px 12px`, radius 999, borde `1px
  #2a2b32`; activo bg `#22232a` y texto `#e7e7ea`. Entre grupos, una raya de
  `1px × 20px` `#2a2b32`. La fila: `display: flex; gap: 6px; overflow-x: auto;
  scrollbar-width: none; padding: 0 16px`, con `scroll-padding-inline: 16px`.
- **Zona de toque de 44px** sin agrandar el chip: la fila tiene `padding-block:
  5px` y cada chip un `::after` con `inset: -5px -3px` (el dibujo mide 34px).
- **`shell.js`:**
  - `setActive(link)` hoy sólo enciende en `.sidebar`. Pasa a encender el link
    tocado y su gemelo (mismo `href`) en la otra lista: barra lateral ↔ fila
    de chips, respetando `data-apart` en las dos.
  - `sideFilters()` (que en Ocio reemplaza los grupos de la barra lateral con
    los que trae la respuesta de la columna) reemplaza también la fila: la
    respuesta de `/ocio/lista` suma `filter-chips.html` igual que hoy suma
    `sidebar-filters.html`.
  - Al cargar y después de cada cambio, el chip encendido se trae a la vista
    (`scrollIntoView({inline: "nearest", block: "nearest"})`), sin mover la
    página.

## 4. Campo unificado y cabecera de lista

**Campo** (`.unified`, debajo de 60rem): `padding: 0 16px 12px`, sin borde
inferior; input de 46px, radius 12, **16px** de letra (decisión), con el
placeholder de cada sección como hoy (§15). El `kbd` `/` no se ve.

- **Modo guardar** (link pegado): el formulario hace `flex-wrap: wrap` y
  `.save` pasa a una fila propia a todo el ancho, con tres partes iguales como
  el mockup: Completo · Resumen · Guardar. 14px, `padding: 11px`, radius 10.
  El segmentado deja de ser una pastilla: cada opción es un botón con borde
  `#2a2b32`, la marcada bg `#2a2c34`.
- Ocio, "Buscar en los catálogos ↵", e Ideas, "Nueva idea ↵": el mismo
  renglón propio, el botón a todo el ancho.
- Los `↵` de los botones pasan a `<span class="enter-hint" aria-hidden="true">↵</span>`
  (también "Abrir original ↵" del panel). `pointer: coarse` los esconde.

**Cabecera de lista** (`.list-head`): `padding: 0 16px 8px`. Izquierda
"{filtro} · N"; derecha, en este orden, **Seleccionar** (§9) y el segmentado
Lista | Tarjetas con opciones de 44px de alto (padding `7px 14px` + zona de
toque). En Ocio, el aviso "• N fichas sin reescribir [Reescribir]" baja a su
propio renglón (`flex-basis: 100%`) y "Recientes ▾" queda a la derecha.

## 5. Las listas

| | Debajo de 42rem | 42–60rem |
|---|---|---|
| Biblioteca, Tarjetas | 2 columnas, gap 10, `grid-auto-rows: max-content`; miniatura de 84px; dominio Mono 10px; cuerpo `9px 10px 11px`, título 13.5/500 a 2 líneas; el renglón "punto · Categoría · fecha" se mantiene | 3 columnas |
| Biblioteca, Lista | grid `8px minmax(0,1fr) auto`, `min-height: 44px`, padding `10px`, borde inferior `#1d1e23` en vez de radius; título 15/500 con ellipsis, debajo el dominio 12px, a la derecha la fecha Mono 11px (mockup) | igual |
| Ocio, pósters | 2 columnas `minmax(0,1fr)`, gap 12 | `auto-fill, minmax(168px, 1fr)` |
| Ideas, Tarjetas | 1 columna | 2 columnas |
| Ideas, Lista | como la Biblioteca | igual |

- `.list-body`: `padding: 0 16px 12px` (filas: `0 8px`), más
  `var(--tabbar-h)` abajo.
- Estados vacíos: `margin-top: 10vh` en vez de 18vh, `padding: 0 16px`.
- El resaltado `.on` del ítem elegido no se dibuja en el celular (no hay panel
  al lado que lo explique), salvo el cursor de teclado si hay teclado (§10).

## 6. El detalle a pantalla completa

### 6.1 Markup

- `<section class="detail" id="panel">` lleva `data-open` cuando la URL trae
  `sel` y ese id está en la lista (lo que hoy ya resuelve `current`). Lo mismo
  con la búsqueda de catálogos de Ocio (`buscar=`). En escritorio el atributo no
  cambia nada.
- `panel.html`, `card-panel.html` y `catalog-panel.html` empiezan con el
  partial nuevo `detail-back.html`:
  `<a class="detail-back" href="{{ view.url(sel='') }}" data-back>← {{ sección }}</a>`
  (Biblioteca u Ocio). En escritorio no se ve. Sin JS es un link común que
  vuelve a la lista.

### 6.2 Debajo de 60rem

```
.detail:not([data-open])  display: none
.detail[data-open]        position: fixed; inset: 0; z-index: 40; bg #141519;
                          display: flex; flex-direction: column;
                          padding-top: env(safe-area-inset-top)
```

- `.detail-back`: renglón de 44px, `padding: 0 16px`, 14px `#a9b4de`.
- `.detail-scroll`: `padding: 12px 16px 24px`, gap 16. Título 22px (26 no
  entra en dos líneas a 390). Cuerpo 15/1.65 como escritorio.
- `.detail-bar` (Biblioteca) fija abajo de la capa: `padding: 10px 16px
  max(10px, env(safe-area-inset-bottom))`, botones de 44px de alto
  (`.btn` pasa de 32 a 44 dentro de la capa), ★ y ⋯ de 44×44.
- **Ocio, `.card-top`:** `flex-wrap: wrap`, `padding: 10px 16px`. Renglón 1:
  segmentado Por ver | Viendo | Vista (cada opción ≥44px de alto) y ⋯ a la
  derecha; renglón 2: las 5 estrellas, cada botón 44×44 con el dibujo de 19px.
  `.card-head` pasa a `88px minmax(0,1fr)`; el título 20px.
- Las pestañas de abajo quedan tapadas por la capa (z-index), y el toast
  (z 50) queda encima.

### 6.3 Abrir, volver, Esc

En `shell.js`, sólo cuando `oknowledge.phone()`:

- **Tocar** un `a[data-sel]`: `loadPanel(id, false, {push: true})`. Con
  `push`, en vez de `replaceState` hace
  `history.pushState({layer: "panel"}, "", url)` y pone `data-open`. Tocar
  otro ítem con la capa ya abierta no pasa: la capa tapa la lista.
- **`popstate`**: si la URL ya no tiene `sel` (ni `buscar`), saca `data-open`.
  Si tiene, la abre y carga ese id (adelante después de atrás). La lista no se
  vuelve a pedir: está debajo, con su scroll.
- **"← Biblioteca" / Esc / `oknowledge.layers.close()`**: si
  `history.state && history.state.layer === "panel"`, `history.back()` (el
  `popstate` cierra). Si no (la página arrancó con `sel=`), `replaceState` sin
  `sel` y cierra. Nunca se sale del sitio.
- **Esc** en `app.js`: el orden de la entrega 3 suma un paso, después de
  "cierra el modal abierto" y antes de los menús: "si hay una capa abierta, la
  cierra".
- **Movimiento sin abrir**: `j`/`k`/flechas, el panel que sigue después de un
  borrado y la recarga del poller usan `loadPanel` sin `push`: en el celular
  cargan el panel sin abrir la capa.
- **Borrar desde el ⋯** (link o ficha): al volver con `undo`, en el celular
  cierra la capa (como "←") en lugar de abrir el que seguía, recarga la lista y
  muestra el toast con Deshacer. Deshacer recarga la lista y no abre nada.
- **Guardar un link** desde el campo: la redirección de hoy, `/?sel=<nuevo>`,
  abre la capa con el esqueleto "La IA está leyendo el link…". Atrás vuelve a
  la lista (con la página recién cargada no hay entrada propia: es el caso
  `replaceState`).
- **Ocio, "Buscar en los catálogos"**: `showCatalog` hace lo mismo que
  `loadPanel` con `push`. Elegir un candidato guarda y redirige como hoy
  (`/ocio?sel=…`): la capa se abre con la ficha nueva.
- **Ayudante común** en `app.js`, `oknowledge.layers`: `open(name, onClose)`
  hace el `pushState({layer: name})`; un único `popstate` llama al `onClose`
  de la capa de arriba; `close()` es el "←" de arriba. Lo usan el panel y el
  modal de Ajustes (§8). Las capas no se apilan más de una: abrir Ajustes con
  el detalle abierto no pasa (la barra de arriba queda tapada).

## 7. La pantalla de una idea

Debajo de 60rem, `.app.idea-screen` deja la grilla de tres columnas: una sola
columna que scrollea como página (§2.2), en este orden:

1. **Cabecera** (`padding: 12px 16px`): fila meta "← Ideas · creada 13 oct ·
   Guardado"; el título (el input de hoy, 22px; un título largo se corta con
   ellipsis y se lee entero al editarlo, para no tocar `autosave.js`); debajo `.idea-controls` con `flex-wrap: wrap`: segmentado de
   estado (scroll horizontal si no entra), estrellas de 44px, ⋯. Etiquetas.
2. **Barra de IA**: `overflow-x: auto`, sin envolver; "PEDILE A LA IA" no se ve
   (`.label` oculto), quedan los botones (44px de alto), "usando" y el alcance.
   El estado de trabajo ("Mejoras…") baja a su propio renglón.
3. **TU IDEA**: textarea con `min-height: 40dvh`, 16px.
4. **Resultados**: las pestañas Resumen | ¿Ya existe? | Mejoras | Ampliación
   con scroll horizontal; el contenido sin scroll propio (scrollea la página).
5. **Links de esta idea** (`.links-column`): sin borde izquierdo, borde
   superior; buscador de 44px y 16px; sus filas de 44px; "+ Sumar" y ✕ con
   zona de 44px.

Sólo CSS. "← Ideas" es el link de hoy; atrás del navegador vuelve a la lista
porque llegar a la idea fue una navegación común.

## 8. Ajustes, Atajos y menús

**Ajustes** (`dialog.modal.settings`, debajo de 60rem): `width: 100vw;
height: 100dvh; max-width: none; max-height: none; margin: 0; border: 0;
border-radius: 0`, padding de safe-area arriba y abajo.
- Cabecera: "Ajustes" y ✕ de 44×44; "Los cambios se guardan solos" baja debajo
  del título.
- Pestañas: `overflow-x: auto`, sin envolver, cada una de 44px de alto.
- **Motores:** `.engine-row` en una columna: checkbox + nombre en un renglón,
  el input de modelo a todo el ancho, "Buscar modelos" y la fecha abajo.
  Proveedores con renglones de 44px (como hoy hace `style.css` en la página
  vieja).
- **Idioma y guardado:** `.setting` apilado: etiqueta y hint arriba, el
  segmentado debajo a todo el ancho con opciones de 44px.
- **Importar:** con `pointer: coarse`, "Soltá acá el export de WhatsApp" no se
  ve (no hay de dónde arrastrar); quedan las instrucciones y "Elegir archivo"
  como botón de 44px.
- **Categorías:** cada fila en dos renglones (punto, nombre y contador; el
  input a todo el ancho).
- Inputs a 16px.
- **Atrás** lo cierra: `app.js`, al abrirlo con `oknowledge.phone()`, usa
  `oknowledge.layers.open("settings", cerrar)`; ✕ y Esc pasan por
  `layers.close()`. En escritorio no hay entrada de historial.
- La página `/settings` (sin JS o por URL) es una página vieja (§11).

**Atajos** (`dialog.keys`): no cambia; no hay cómo abrirlo con el dedo. Con
teclado físico, `?` lo abre con su `max-width: calc(100vw - 32px)` de hoy.

**Menús** (`details.menu`: chip de categoría, "A una idea ▾", ⋯, "Mover a ▾",
"Recientes ▾", el alcance de la IA): debajo de 60rem, `.menu-list` es
`position: fixed; left: 0; right: 0; bottom: 0; top: auto; min-width: 0;
max-height: 60dvh; border-radius: 14px 14px 0 0; padding-bottom:
max(8px, env(safe-area-inset-bottom)); z-index: 45`, con ítems de 44px. El
fondo: `.menu[open] > summary::before { content: ""; position: fixed; inset: 0;
background: #0009; z-index: 44 }`, que al tocarlo toca el `summary` y cierra.
Los submenús (Cambiar tipo ▸) se despliegan dentro de la hoja. Sólo CSS: la
regla de "uno cierra al otro" y Esc de `app.js` siguen igual.

## 9. Selección múltiple, barra de lote y toast

**Checkbox con dedo.**
- `@media (hover: none)` (cualquier ancho): `.check { opacity: 1 }`. Es el
  arreglo para tablets en escritorio.
- Debajo de 60rem los checkboxes **no** se ven salvo en modo selección: dos
  columnas de tarjetas con una casilla en cada una es ruido, y el dedo no los
  pide sin querer.

**Modo selección** (sólo celular, sólo con JS):
- `list.html`, `ocio-list.html` e `idea-list.html` suman en `.list-head`
  `<button type="button" class="btn select-mode js-only" data-select-mode
  data-on="Cancelar" aria-pressed="false">Seleccionar</button>`, visible sólo
  debajo de 60rem.
- `select.js`: el botón pone/saca `selecting` en `#list` y cambia su texto
  ("Seleccionar" ↔ "Cancelar", `aria-pressed`). Con `selecting`:
  - se ven los checkboxes; la zona de toque del `label.check` es de 44×44 (el
    dibujo sigue de 18px; en celular 22px);
  - tocar un ítem (`a.hit`) lo marca o desmarca en vez de abrirlo: un listener
    de `click` en `#list` en fase de captura hace `preventDefault()` y
    `stopPropagation()` antes que el de `shell.js`;
  - en Ocio el chip de tipo se corre como con `.picking`.
- **Mantener apretado** (respuesta 4 del usuario, 2026-10-15) es la otra
  entrada, sólo debajo de 60rem (`window.oknowledge.phone()`): en `select.js`,
  con pointer events, un `pointerdown` sobre un ítem con casilla
  (`a.hit` → `li.item` → `input[name=ids]`) arma un timer de 500 ms; si el dedo
  no se mueve más de 10px, prende el modo (el mismo camino que "Seleccionar") y
  marca ese ítem. El `click` que trae el soltar se traga (ni abre el detalle ni
  desmarca), sólo ese; el siguiente `pointerdown` olvida la espera si el click
  no llegó. `contextmenu` del apretón que entró se cancela; si llega antes de
  los 500 ms (Android lo manda más o menos a la vez, y después un
  `pointercancel`), dispara el apretón en ese momento y también se cancela. En el bloque del
  celular `#list .item` lleva `-webkit-touch-callout: none` y
  `user-select: none`. No hacen nada: moverse más de 10px (un scroll),
  `pointercancel`, soltar antes, el botón derecho del mouse, un ítem que se está
  analizando (no tiene casilla: su click es un toque y lo abre), estar ya en
  modo selección (el click es un toque más y marca o desmarca) y el escritorio
  (≥60rem).
- Se sale con "Cancelar", ✕ de la barra, Esc, un cambio de filtro, búsqueda u
  orden (`oknowledge:list` con `reason: "filter"`, igual que la selección) y
  después de una acción en lote que salió bien. Salir limpia lo marcado.

**Barra de lote** debajo de 60rem: `position: fixed; left: 8px; right: 8px;
bottom: max(8px, env(safe-area-inset-bottom)); transform: none; width: auto;
justify-content: space-between`, botones de 44px. "★ Favorito" muestra sólo ★
(con `aria-label` "Favorito"). "Mover a ▾" abre su lista como hoja (§8); el
input "Nueva categoría" queda arriba de la hoja, a 16px.
- **Con las pestañas:** mientras `#list.selecting` o la barra se ve, las
  pestañas no se dibujan: `body:has(#list.selecting, #bulk:not([hidden]))
  .tabbar { display: none }`. La barra ocupa su lugar y `.center` mantiene el
  mismo `padding-bottom`.
- La barra aparece con ≥1 marcado, como hoy. En modo selección con 0 marcados
  no hay barra ni pestañas: el "Cancelar" de arriba es la salida.

**Toast** debajo de 60rem: `top: calc(env(safe-area-inset-top) + 12px)`,
`max-width: calc(100vw - 32px)`, `white-space: normal`, el botón Deshacer con
zona de 44px de alto. Sigue arriba al centro: nunca tapa ni la barra de lote ni
las pestañas.

## 10. Teclado

Nada nuevo ni nada quitado. En el celular no hay ayuda visible ni hints, y las
teclas sólo se usan con un teclado físico. Dos detalles:
- `j`/`k`/flechas eligen el ítem (y se dibuja el cursor `.on` sólo si el último
  evento fue de teclado: clase `keyed` en `#list` (sobrevive al redibujo de la lista), que el primer `pointerdown`
  saca) pero no abren la capa; Enter sigue abriendo el original.
- Esc suma el paso de la capa (§6.3) y sale del modo selección (§9).

## 11. Páginas viejas

`/settings` (página), `/import`, `/retry`, `notfound.html`, `error.html` y lo
que siga con `.app.legacy`: barra de arriba + `legacy-main` que scrollea como
página + pestañas. `legacy-main`: `padding: 12px 16px var(--tabbar-h)`. Se
revisan a 390px buscando desbordes (la vista previa de WhatsApp, la tabla de
Actividad) y se arreglan con `min-width: 0`, `overflow-wrap: anywhere` en
URLs y tablas con scroll propio. Sin rediseño.

## 12. Objetivos táctiles, safe areas y scroll horizontal

**`<meta name="viewport" content="width=device-width, initial-scale=1,
viewport-fit=cover">`** en `base.html`. Sin `maximum-scale`: el pellizco para
acercar sigue andando.

**≥44px** (alto, y ancho donde es un ícono): pestañas; "Ajustes"; "← volver";
"Seleccionar"/"Cancelar"; Lista/Tarjetas; `.btn` y `.btn.icon` dentro de la
capa, la barra de lote y Ajustes; ítems de menú; estrellas del detalle y de
la idea; segmentados de estado; checkbox (zona); chips de filtro y de
etiqueta del detalle (zona, por `::after`); ✕ de una etiqueta (zona de 32×44,
al lado del texto); "+ etiqueta" (alto). Filas de lista ≥44px.

**Sin scroll horizontal**, regla por regla:
- `.toast` y `.bulk`: `white-space: normal` / ancho fijo a la pantalla (§9).
- `.menu-list`: hoja a todo el ancho (§8); el `min-width: 200px` no aplica.
- `.engine-row`, `.cat-row`, `.setting`: una columna (§8).
- `.idea-ai`, `.idea-results .tabs`, `.settings-tabs`, `.chip-row`,
  `.seg` de estado: scroll horizontal propio, no de la página.
- `.card-top`, `.idea-controls`, `.list-head`: `flex-wrap: wrap`.
- Títulos y URLs: `overflow-wrap: anywhere` en `.detail h1`, `.where`, la
  menciones y `pre` del contenido original (`overflow-x: auto`).
- Red: `.app { overflow-x: clip }`.

## 13. JavaScript: quién hace qué

| Archivo | Cambia |
|---|---|
| `static/app.js` | `oknowledge.phone()` (un `matchMedia` de 60rem); `oknowledge.layers` (`open`, `close`, un `popstate`); Esc cierra la capa; Ajustes usa `layers` en el celular |
| `static/shell.js` | `loadPanel(id, gone, {push})` y `showCatalog` con `push` en el celular; `data-open` en `#panel`; `popstate` abre/cierra; `[data-back]`; tras borrar desde la capa, cierra en vez de abrir el siguiente; `setActive` y `sideFilters` también en la fila de chips; chip encendido a la vista; clase `keyed` |
| `static/select.js` | botón `[data-select-mode]`, clase `selecting`, toque que marca en vez de abrir (captura), salida del modo |
| `static/layout.js` | pierde el plegado de `details.filters` y el `autofocus` de la búsqueda vieja (código muerto); conserva la clase `js` y la limpieza de `notice`/`n`/`m`/`undo` |

Nada nuevo se carga: el celular usa los mismos archivos que la entrega 3.

## 14. Sin JavaScript

- El armazón, la fila de chips, las pestañas, los menús como hoja y Ajustes
  como página son CSS y HTML: andan igual.
- Tocar una tarjeta es el link de hoy, `?sel=<id>`: la página vuelve con
  `#panel[data-open]` y el detalle a pantalla completa. "← Biblioteca" es un
  link a la lista sin `sel`; atrás del navegador también vuelve (es una
  navegación común).
- Filtros: cada chip es un link; la página entera se recarga.
- No hay modo selección, ni barra de lote, ni Ajustes en modal, como en la
  entrega 3.

## 15. Textos

Claves en inglés y castellano en `i18n.py`. Se reusan "Library", "Leisure",
"Ideas", "Favorites", "Settings", "Sections", "Select". Nuevas:
"Cancel" → "Cancelar" (si no existe), "Filters" → "Filtros" (`aria-label` de la
fila), "Back to %1" → "Volver a %1" (`aria-label` de "←"). "Pinned" ya existe
("Fijados").

El placeholder del campo de la Biblioteca **no** cambia: el mockup dice "Buscá
o pegá un link", pero un CSS no puede cambiar un placeholder. El largo ("Buscá
o pegá un link para guardarlo") entra a 390px con 16px de letra.

El de **Ocio** sí (pedido del usuario, 2026-10-15): "Buscá en Ocio o pegá un
link de IMDb u Open Library" se cortaba a 390px. Clave nueva "Search or paste
an IMDb link" → "Buscá o pegá un link de IMDb", en
`data-short-placeholder` del `#field-q` de `ocio-shelf.html`. `app.js` (dueño
de la media query de 60rem) pone el corto mientras el celular coincide y
devuelve el largo cuando deja de coincidir. El escritorio y sin JS muestran el
largo; `aria-label` es el largo siempre.

## 16. Pruebas

**pytest + TestClient** (`tests/test_web_phone.py`, nuevo; los de
`test_web_layout.py` que prueban el celular viejo se reescriben o se van):
- `base.html`: `viewport-fit=cover`; `.topbar` con el logo y "Ajustes"
  `data-modal="settings"` y el contador del lote; `.tabbar` con cuatro links
  (`/`, `/ocio`, `/ideas`, `/?mark=%E2%AD%90`) en toda página (las tres
  secciones, `/ideas/{id}`, `/settings`, `/import`, `/retry`, un 404).
- Pestaña activa: `/` → Biblioteca; `/?mark=⭐` → Favoritos y no Biblioteca;
  `/?mark=⭐&q=x` → Biblioteca; `/ocio`; `/ideas`; `/ideas/{id}` → Ideas.
- `.chip-row`: en la Biblioteca, Todo + categorías + marcas + colecciones, sin
  ★ Favoritos, el chip encendido según `cat`/`mark`/`col`, `title` con la
  cuenta; en Ocio dos grupos `data-apart` y la respuesta de `/ocio/lista` trae
  la fila; en Ideas el grupo ESTADO; un grupo vacío no se dibuja.
- `#panel[data-open]` con `?sel=<id existente>` (Biblioteca y Ocio) y con
  `?buscar=` en Ocio; sin `sel`, o con un `sel` que no está, no lo lleva.
- `panel.html`, `card-panel.html`, `catalog-panel.html` (también por
  `/panel/{id}`) empiezan con `a.detail-back[data-back]` cuyo `href` es la
  lista sin `sel` (con los demás filtros).
- `.list-head` de las tres listas trae `button[data-select-mode].js-only`.
- Los `↵` van en `span.enter-hint[aria-hidden]`.
- CSS (texto de `app.css`): el bloque `max-width: 60rem` existe una vez, usa
  `100dvh` y `env(safe-area-inset-bottom)`; `(hover: none)` muestra `.check`;
  `(pointer: coarse)` esconde `.key`, `.enter-hint` y "Atajos"; no queda el
  bloque "sin pulir".
- JS (texto + `node --check`): `layout.js` ya no nombra `details.filters`;
  `shell.js` usa `pushState` sólo detrás de `oknowledge.phone()`; `app.js`
  define `layers`.

**Playwright** (node en `$SP/pw`, `executablePath: "/usr/bin/chromium"`,
contexto `viewport 390×844`, `isMobile: true`, `hasTouch: true`,
`deviceScaleFactor: 3`) sobre un vault de prueba con muchas categorías (que la
fila de chips desborde), 30 links, 6 fichas, 4 ideas, un link analizándose:
- **Sin scroll horizontal:** en `/`, `/?vista=lista`, `/?mark=⭐`, `/ocio`,
  `/ideas`, `/ideas?vista=lista`, `/ideas/{id}`, `/settings`, `/import`,
  `/retry`, con el detalle abierto, con Ajustes abierto, con un menú abierto,
  con la barra de lote y con un link pegado en el campo:
  `document.documentElement.scrollWidth <= innerWidth`. La fila de chips sí
  scrollea (`scrollWidth > clientWidth`).
- **Pestañas:** visibles, su borde inferior en 844, cuatro, cada una ≥44×44,
  la activa correcta; tocarlas navega.
- **Objetivos ≥44px:** recorre `.tabbar a`, `.topbar a`, `.detail-back`,
  `.detail-bar .btn`, `.card-top button`, `.list-head .seg a`,
  `[data-select-mode]`, `.bulk button`, `.bulk summary`, `.menu-list button`
  (con un menú abierto), `label.check` (en modo selección) y mide
  `getBoundingClientRect()` (o la zona del `::after`, con
  `elementFromPoint` a 21px del centro) ≥ 44.
- **Detalle:** tocar una tarjeta → `#panel` cubre `0,0,390,844`, la URL trae
  `sel`, `history.length` sube 1; `page.goBack()` → la capa se cierra, la URL
  sigue en `/` sin `sel` y el scroll de la lista es el de antes;
  `goForward()` la vuelve a abrir. Recargar con `?sel=` abre la capa, y
  "← Biblioteca" la cierra sin salir del sitio (la URL queda en `/`). Esc la
  cierra. Lo mismo en Ocio con un póster y con "Buscar en los catálogos".
- **Borrar desde el ⋯ de la capa:** se cierra, toast con Deshacer dentro de la
  pantalla, Deshacer devuelve la nota a la lista.
- **Ajustes:** "Ajustes" de la barra de arriba abre el modal a pantalla
  completa; `goBack()` lo cierra y deja la página; las cuatro pestañas se
  alcanzan; un cambio se autoguarda.
- **Selección:** "Seleccionar" → checkboxes visibles; tocar dos tarjetas las
  marca sin abrir la capa; la barra de lote se ve, dentro de la pantalla, y
  las pestañas no; "Mover a ▾" como hoja; Borrar → toast con Deshacer;
  "Cancelar" vuelve a las pestañas.
- **Campo:** con un link pegado, Completo · Resumen · Guardar en un renglón
  propio; el input mide 46px y su letra es ≥16px.
- **Escritorio táctil:** contexto 1280×800 con `hasTouch` → `.check` visible
  sin hover, "Atajos" no.
- **Escritorio sin cambios:** 1440×900 sin touch: `.topbar`, `.tabbar` y
  `.chip-row` no se ven, el panel está en la grilla, sin `data-back` visible;
  las capturas de las entregas 1 a 3 no cambian.
- **42–60rem:** 768×1024 → tarjetas de la Biblioteca en 3 columnas, Ideas en
  2, sigue sin scroll horizontal.
- **Sin JS** (`javaScriptEnabled: false`, 390×844): tocar una tarjeta navega a
  `?sel=` con la capa abierta; "← Biblioteca" vuelve; un chip filtra; no hay
  "Seleccionar".
- **Capturas** a 390×844 de cada pantalla, comparadas a ojo con `1a celular`.
- La suite completa en verde. El vault real y `~/.config/oknowledge` no se
  tocan.

## Fuera de alcance

- PWA: manifest, ícono, instalar, service worker, modo sin conexión.
- "Compartir con oknowledge" desde otra app (Web Share Target).
- Gestos más allá de tocar y atrás: deslizar para cerrar la capa o para
  volver, long-press para seleccionar, pull-to-refresh, deslizar en las
  pestañas.
- Bottom sheet arrastrable con alturas intermedias.
- Un armado propio para tablet (dos columnas lista + panel entre 42 y 75rem) y
  el escritorio apretado entre 60 y ~70rem.
- Tema claro.
- Selección con rangos y "seleccionar todo" (como en la entrega 3).
- Rediseño de `/import`, `/retry` y la página `/settings`: sólo se arreglan
  desbordes.
- Llevarlo a la rama `windows` del fork: después del merge en `main`, como
  las anteriores.

## Preguntas para el usuario

Respondidas el 2026-10-15:

1. **Favoritos:** alcanza con la Biblioteca filtrada por ★ (como está).
2. **Detalle:** pantalla completa (como está).
3. **Corte:** 60rem (como está).
4. **Seleccionar:** el botón queda, y además mantener apretado un ítem entra al
   modo y lo marca (§9).
5. **Fila de chips:** sin chip "Más ▾"; la fila sigue con scroll horizontal.

Además: el placeholder de Ocio se acorta en el celular (§15).
