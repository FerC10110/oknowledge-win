# Rediseño, entrega 3: modales, teclado, selección múltiple y Deshacer

**Fecha:** 2026-10-14 · **Rama:** `feat/rediseno-modales-teclado`
**Referencia visual:** `design_handoff_oknowledge_redesign/README.md` §4 Ajustes,
§5 Ayuda de atajos, §6 Toast, "Barra de selección múltiple", "Interactions &
Behavior" y los tokens; el `<script>` de `oknowledge App.dc.html` como
especificación de estados; capturas `03`, `07`, `08` y `09`. Los números exactos
(px, colores, radios) salen del README.
**Base:** entregas 1 y 2 (`2026-10-14-rediseno-biblioteca-design.md`,
`2026-10-14-rediseno-ocio-ideas-design.md`): tokens, barra lateral, campo
unificado, autoguardado con `Accept: application/json` y `answer()` valen acá
salvo donde este documento dice otra cosa.

> El usuario aprobó seguir solo durante la noche. Las decisiones de abajo las
> tomó el controlador o esta spec sin consultarlo: todas van marcadas para que
> las revise.

## Decisiones tomadas

| Pregunta | Respuesta | |
|---|---|---|
| ¿Ajustes? | Modal sobre la pantalla actual, desde "Ajustes" del pie. El JS pide un fragmento armado por el servidor. `/settings` sigue como página para quien no tiene JS o entra por URL: mismos campos, mismas rutas | decidido sin consultar (revisar) |
| ¿Pestañas de Ajustes? | **Motores**, **Idioma y guardado**, **Importar** y una 4.ª, **Categorías** (renombrar). Sigue la línea de la entrega 1 ("los dos primeros pasan adentro de Ajustes") y se aparta de las 3 del handoff | decidido sin consultar (revisar) |
| ¿Actividad? | Sale del pie. Importar muestra "Links esperando análisis: N", el botón para analizarlos y un link a la página Actividad (`/retry`), que sigue existiendo | decidido sin consultar (revisar) |
| ¿Guardar en Ajustes? | Todo se autoguarda (al cambiar o salir del campo; JSON por `answer()`). Sin botones Guardar en el modal. "Los cambios se guardan solos" en la cabecera | decidido sin consultar (revisar) |
| ¿Pie de la barra lateral? | "Atajos ?" + "Ajustes" | decidido sin consultar (revisar) |
| ¿Un ajuste que necesita recargar (idioma de la interfaz)? | El modal lo avisa y recarga la página apenas se guarda | decidido sin consultar (revisar) |
| ¿Ayuda de atajos? | Modal de 420px con la grilla tecla/descripción; se abre con `?` o desde el pie. Va en la página, oculto | decidido sin consultar (revisar) |
| ¿Teclado? | La tabla del README, con las reglas por pantalla de §4 | decidido sin consultar (revisar) |
| ¿Selección múltiple? | Checkboxes en tarjetas y filas de la Biblioteca, pósters de Ocio y filas o tarjetas de Ideas. Barra flotante: N seleccionados · Mover a ▾ · ★ Favorito (sólo Biblioteca) · Borrar · ✕. Sólo con JS | decidido sin consultar (revisar) |
| ¿Deshacer? | Borrar (uno desde ⋯, o en lote) da un toast con **Deshacer** por 5 s. `POST /undo/{token}` devuelve las notas a su lugar. Vale para links, fichas e ideas | decidido sin consultar (revisar) |
| ¿Toast? | Uno solo para toda la app (arriba al centro). 2,2 s; 5 s con Deshacer | decidido sin consultar (revisar) |
| ¿Menús? | Abrir uno cierra el otro; Esc los cierra. Ya pasaba en las listas (`shell.js`), pero no en la pantalla de una idea ni en Ajustes: la regla pasa a un archivo que carga toda página | decidido sin consultar (revisar) |
| **¿Dónde quedan los archivos borrados?** | **Donde van hoy, en `<vault>/oknowledge/trash/`. En el state dir (`$XDG_STATE_HOME/oknowledge/undo/`) va sólo el lote: un JSON con qué archivo salió de dónde.** La regla pedía mover los archivos al state dir y purgarlos a las 24 h. Eso borraría notas para siempre a las 24 h, y hoy viven en `trash/` indefinidamente: rompe la regla 3 de `vault.py` ("Nothing is destroyed"). Además el state dir puede estar en otro disco que el vault, y ahí la mudanza deja de ser atómica. Sin JS, el aviso "podés restaurarla desde Obsidian" sigue siendo cierto. Contra: Obsidian sigue mostrando `trash/`, como hoy | decidido sin consultar (revisar) |
| ¿Cuándo vence un Deshacer? | A las 24 h. Los lotes vencidos se borran al arrancar la app y cada vez que se crea uno nuevo, porque el servidor puede correr semanas (`idle_timeout 0`). Purgar un lote borra sólo el JSON, nunca una nota | decidido sin consultar (revisar) |
| ¿Confirmar al borrar? | Se va el `confirm()` de Borrar (link, ficha, idea): Deshacer lo reemplaza. Reprocesar mantiene el suyo | decidido sin consultar (revisar) |
| ¿Importar WhatsApp desde el modal? | La zona de drop y "Elegir archivo" postean a `/import` como hoy, y la vista previa y la confirmación siguen en la página `/import`: el modal se deja atrás. Pasarlas adentro del modal duplicaría una página de tres estados que ya funciona | decidido sin consultar (revisar) |
| ¿Página `/categories`? | Redirige (303) a `/settings?tab=categorias`. `categories.html` se va | decidido sin consultar (revisar) |
| ¿Renombrar categorías con autoguardado? | Al apretar Enter o salir del campo, si el nombre cambió. Si el nombre nuevo ya existe (unir dos categorías no tiene Deshacer), primero un `confirm()` | decidido sin consultar (revisar) |
| ¿`POST /settings` parcial? | Cada pestaña es su propio formulario. Un campo que no llega queda como está; hoy un modelo que no llega se borra | decidido sin consultar (revisar) |
| ¿Progreso de un lote en el pie? | El contador que hoy lleva "Actividad" (`3/10`) pasa al link "Ajustes" | decidido sin consultar (revisar) |
| ¿Backspace sin nada marcado? | No hace nada: sólo borra los marcados, como dice la tabla | decidido sin consultar (revisar) |
| ¿★ Favorito en lote? | Si todos los marcados ya son ⭐, se la saca a todos; si no, se la pone a todos (reemplaza otra marca, como la ★ del panel) | decidido sin consultar (revisar) |
| ¿Checkbox en un póster? | Arriba a la izquierda, como en las tarjetas; el chip de tipo se corre a su derecha | decidido sin consultar (revisar) |
| ¿Qué pasa con la selección al recargar la lista? | Sobrevive a las recargas de la misma lista (fin de un análisis, una edición, "más"); se limpia al cambiar de sección, filtro, búsqueda u orden, con Esc y después de una acción en lote que salió bien | decidido sin consultar (revisar) |
| ¿j/k en la lista de Ideas, que no tiene panel? | Mueven un cursor (la fila resaltada); Enter abre la idea | decidido sin consultar (revisar) |
| ¿Qué muestra el panel después de borrar el elegido? | El que le seguía en la lista (o el anterior si era el último; vacío si no queda ninguno) | decidido sin consultar (revisar) |

## 1. JavaScript: quién hace qué

| Archivo | Dónde carga | Qué hace |
|---|---|---|
| `static/app.js` (nuevo) | toda página, desde `base.html`, `defer`, antes que los demás | crea `window.oknowledge` con `toast()` y `closeMenus()`; la regla de los menús; los dos modales; las teclas globales (`?`, `1` `2` `3`, `/`, Esc); el Deshacer de un toast que dibujó el servidor |
| `static/settings.js` (cambia) | toda página, desde `base.html` | el autoguardado de Ajustes, el selector de modelos, renombrar categorías, la zona de drop. Se engancha a la página `/settings` y a cada fragmento que trae el modal (`oknowledge.bindSettings(root)`) |
| `static/shell.js` (cambia) | Biblioteca, Ocio, lista de Ideas | además de lo de hoy: las teclas de lista (§4), borrar con Deshacer desde el panel; expone `oknowledge.list = {pick(id), reload(), current()}` |
| `static/select.js` (nuevo) | Biblioteca, Ocio, lista de Ideas | checkboxes, barra flotante, `x`, Backspace/Delete, Esc limpia, rutas en lote |
| `static/autosave.js` (cambia) | Ocio, pantalla de una idea | pierde su `toast()` y extiende `window.oknowledge` en vez de pisarlo |
| `static/idea.js` (cambia) | pantalla de una idea | usa `oknowledge.toast`; devuelve el foco a "+ etiqueta" después de sumar una |
| `static/layout.js` (cambia) | toda página, sin `defer` | pone la clase `js` en `<html>` antes de la primera pintura y saca también `undo` de la URL junto con `notice`, `n` y `m` |

La clase `js` en `<html>` es lo que muestra lo que sólo tiene sentido con
JavaScript (`.js-only`: checkboxes, hints de tecla, "Atajos"). Sin JS esas
piezas no se ven.

**Menús** (pasa de `shell.js` a `app.js`): abrir un `details.menu` cierra los
demás, un clic afuera los cierra, Esc los cierra. Vale en toda página (pantalla
de una idea, `/settings`, el modal).

## 2. Toast

Un solo elemento en `base.html`, `<div id="toast" class="toast" role="status"
aria-live="polite" hidden>`, arriba al centro, con los tokens del README (fondo
`#e7e7ea`, texto `#141519`, radius 10, padding `9px 14px`, sombra
`0 12px 32px #0008`).

`oknowledge.toast(text, opts)`:
- `opts.action` (texto del botón) y `opts.run` (qué hace): agrega un botón al
  final del toast; al tocarlo corre `run` y el toast se cierra.
- `opts.ms`: duración. Por defecto 2200, o 5000 si hay `action`.
- Un toast nuevo reemplaza al anterior, con su botón.

`shell.js`, `autosave.js` e `idea.js` dejan de tener su propio `toast()`; los
`.toast` sueltos que hoy se agregan a `<body>` desaparecen.

**Avisos del servidor.** Donde hoy se dibuja `notice` como toast (`toast=True`
en el contexto), va dentro de `#toast`, ya visible. El CSS lo esconde a los
2,2 s con la animación de hoy (5 s con la clase `undo`). Si la URL trae
`undo=<token>` válido y vigente (§6), el toast lleva un formulario
`POST /undo/{token}` con un botón **Deshacer** y `back` = la URL actual sin
`notice`, `n`, `m` ni `undo`. Anda sin JS. Con JS, `app.js` toma ese toast,
le pone su temporizador y manda el Deshacer como JSON.

## 3. Modales

Los dos son `<dialog>` abiertos con `showModal()`: fondo `#0009` en
`::backdrop`, foco atrapado, Esc cierra. Ventana: bg `#1b1c21`, borde
`#2e3038`, radius 14. Sin JS no se abren nunca.

### 3.1 Ajustes

**Dónde.** `<dialog id="settings-modal" class="modal settings">` vacío en
`base.html`. 640×520; la cabecera y las pestañas quedan fijas y el cuerpo
scrollea por dentro.

**Abrir.** El link "Ajustes" del pie (`<a href="/settings" data-modal="settings">`)
con JS abre el modal y pide `GET /settings/panel?tab=<tab>` (la última pestaña
abierta en esta página; la primera vez, `motores`). Sin JS va a `/settings`.
En la página `/settings` el link no abre el modal.

**Rutas.**
- `GET /settings/panel?tab=` → fragmento (sin `<html>`) `settings-body.html`:
  cabecera "Ajustes" + "Los cambios se guardan solos" + ✕, las cuatro pestañas
  y las cuatro secciones; sólo la de `tab` sin `hidden`. `tab` es `motores`,
  `idioma`, `importar` o `categorias`; uno desconocido es `motores`.
- `GET /settings?tab=` → la página de hoy (`settings.html`, con la barra
  lateral), que incluye el mismo `settings-body.html`. Las pestañas son
  `<a href="/settings?tab=…" data-settings-tab="…">`: sin JS recargan y con JS
  cambian de sección sin pedir nada. Las secciones llevan
  `data-settings-pane="…"`. No se usan `data-tab`/`data-pane`, que `idea.js`
  ya escucha en toda la página de una idea.
- El contexto de las dos lo arma una sola función, `settings_context()`, que
  sale de la `settings_page()` de hoy y suma `categories`, `owed`, `size` y el
  estado del lote.

**Autoguardado.** Cada sección es un `<form action="/settings" method="post"
data-settings>` con sus campos y nada más. `settings.js`:
- en `change` de cualquier campo (radio, checkbox, número; un texto dispara
  `change` al salir si cambió), manda el formulario entero con
  `Accept: application/json`;
- `{"ok": true}` sin `notice`: no dice nada (la cabecera ya avisa que se guarda
  solo). Un `notice` (por ejemplo `language-not-saved`) o un error van al
  toast, y el campo queda como el usuario lo dejó;
- `{"reload": true}` (cambió el idioma de la interfaz): recarga la página. La
  sección lo avisa debajo del selector: "Cambiarlo recarga la página";
- después de guardar "Guardar por defecto", pone el mismo valor en el
  segmentado Completo | Resumen del campo unificado, si la página lo tiene;
- sin JS, cada formulario tiene su botón Guardar `data-nojs`, que
  `settings.js` esconde.

**`POST /settings`** cambia en dos cosas:
- un campo que no llega queda como está. Hoy `opencode_model`, `ollama_model`
  y `api_model` son `Form("")` y uno vacío borra el modelo: pasan a
  `Form(None)`, y `None` no toca nada. Vacío (`""`) sigue borrando. `chain`
  vacío ya dejaba la cadena como estaba;
- contesta con `answer(request, "/settings?tab=<tab>", notice)`, donde `tab`
  es un campo oculto del formulario. JSON: `{"ok": true, "notice": ""}`;
  `{"ok": true, "notice": "…", "reload": true}` si cambió `ui_language`;
  `settings-failed` es 500 (se suma a `FAILURES`).

**Motores** (`tab=motores`):
- Por motor, en el orden de hoy: checkbox `chain` · nombre · input de modelo ·
  "Buscar modelos" (el formulario `find-{name}` de hoy) y la fecha de la última
  búsqueda. El selector "Agregar un modelo…" suma al input y guarda.
- "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos
  separados por coma."
- El bloque de proveedores de `api` (lista con radio `api_provider`, URL,
  variable de la clave, "Crear ese archivo") queda debajo, visible sólo con `api`
  marcado, como hoy. El texto "Lo marcado en uso es lo guardado: guardá
  primero" se va, porque ahora elegir es guardar.
- La advertencia de clave legible por otros usuarios sigue siempre visible.
- `<details>` "▸ ¿Dónde se guarda esto?": la ruta de `config.toml` y la
  advertencia de reescritura y backup (hoy un recuadro arriba de la página).
- `POST /settings/models/{engine}` y `POST /settings/env` pasan a `answer()`
  con `where="/settings?tab=motores"`. En el modal, al volver, `settings.js`
  toastea el aviso y vuelve a pedir el fragmento, que trae la lista de modelos
  o la clave en su lugar. `env-failed` es 500 y `env-there` 409 en
  `FAILURES`.

**Idioma y guardado** (`tab=idioma`). Filas etiqueta + hint a la izquierda y
segmentado a la derecha (radios con forma de segmentado, como el del campo
unificado):
- Idioma de los resúmenes (`language`).
- Idioma de la interfaz (`ui_language`), con el hint "Compartido con tus otros
  plugins de Omarchy".
- Guardar por defecto (`default_content`), con el hint "Lo que se marca al
  pegar un link".
- Menciones de un video (`mentions`): Herramientas / Todo / Sólo lo discutido.
- Links a analizar por vez (`batch`, número de 60px), con el hint "Cuántos
  procesa cada tanda".

**Importar** (`tab=importar`):
- Zona punteada "Soltá acá el export de WhatsApp", con las instrucciones de
  hoy ("En WhatsApp: abrí el chat, Exportar chat, Sin archivos…") y el botón
  "Elegir archivo". Es el `<form action="/import" method="post"
  enctype="multipart/form-data">` de `import.html`. Con JS, elegir o soltar un
  archivo lo envía y la página navega a `/import` con la vista previa. Sin JS,
  el input y el botón "Leerlo".
- "Links esperando análisis: N" (pendientes y fallidos: lo que cuenta
  `owed()`, igual que hoy). Con N > 0, el botón "Analizar N links"
  (`POST /retry`, en el modal como JSON: toast "Analizando N links" y se vuelve
  a pedir el fragmento). Con un lote corriendo: "Analizando: hechos/total" en
  lugar del botón.
- "Ver actividad →" a `/retry`.
- `POST /retry` pasa a `answer()`. Con JSON, `batch-started` dice "Analizando
  %1 links" (clave nueva, `n` = tamaño del lote) en vez de "esta página vuelve
  sola"; `batch-running` es 409 en `FAILURES`.

**Categorías** (`tab=categorias`):
- Cada categoría de la Biblioteca con su punto, su contador y un input con su
  nombre (`<form action="/categories/rename" data-settings-rename>` con `old`
  oculto). Sin categorías: "Todavía no guardaste nada".
- Con JS, Enter o salir del input con un nombre distinto lo postea como JSON.
  Si el nombre ya es el de otra categoría, primero
  `confirm("¿Unir «X» con «Y»?")`. Al volver: toast con el aviso de hoy ("3
  notas movidas", "unidas", parciales) y se pide el fragmento de nuevo. Al
  cerrar el modal después de un renombre que movió algo, la página se recarga
  para que la barra lateral y la lista muestren el nombre nuevo.
- "Si renombrás a una que ya existe, se unen."
- `POST /categories/rename` pasa a `answer(request, "/settings?tab=categorias",
  code, n=…, m=…)`. `GET /categories` → 303 a `/settings?tab=categorias`.

**Cerrar.** ✕, Esc o clic en el fondo. Lo que se estaba escribiendo en un
texto se guarda al salir del campo, antes de cerrar.

### 3.2 Atajos

`<dialog id="keys-help" class="modal keys">` en `base.html`, ya armado, 420px.
Título "Atajos de teclado" y la grilla de la captura `09`, en este orden:

| Tecla | Texto |
|---|---|
| `/` | Buscar o pegar un link |
| `1` `2` `3` | Biblioteca · Ocio · Ideas |
| `j` `k` `←` `→` | Anterior / siguiente |
| `↑` `↓` | Fila arriba / abajo |
| `↵` | Abrir original |
| `f` | Favorito |
| `e` | Agregar etiqueta |
| `x` | Seleccionar |
| `⌫` | Borrar seleccionados |
| `v` | Lista / tarjetas |
| `esc` | Cerrar / deseleccionar |

Teclas en `<kbd>` (Geist Mono 10px, borde `1px #2a2b32`, radius 4). Se abre con
`?` o con "Atajos" del pie (`<button type="button" class="js-only"
data-modal="keys">Atajos <kbd>?</kbd></button>`). `?` o Esc lo cierran.

## 4. Teclado

**Reglas comunes** (`app.js`, un solo `keydown` en `document`):
- Con Cmd, Ctrl o Alt apretado, nada. Shift sí (`?` lo necesita en muchos
  teclados).
- Con el foco en un `input`, `textarea`, `select` o algo `contenteditable`,
  sólo Esc.
- Con un modal abierto, sólo Esc (y `?` cierra Atajos).
- Enter no se toma si el foco está en un link, un botón o un `summary`: ahí
  Enter ya hace lo suyo.
- Cada pantalla registra sus teclas con `oknowledge.keys[tecla] = fn`; una tecla
  que la pantalla no registró no hace nada.

**Globales** (toda página):
- `/`: foco en el campo marcado `data-slash` (el campo unificado; en la
  pantalla de una idea, el buscador de links). `preventDefault`, para que la
  barra no se escriba.
- `1` `2` `3`: van a `/`, `/ocio`, `/ideas`.
- `?`: abre o cierra Atajos.
- Esc: cierra el modal abierto; si no, cierra los menús abiertos; si no había
  menú, saca el foco del campo; si no había nada de eso, limpia la selección.

**De lista** (`shell.js` y `select.js`), por pantalla:

| Tecla | Biblioteca | Ocio | Lista de Ideas |
|---|---|---|---|
| `j` `→` / `k` `←` | elige el siguiente / anterior (panel) | igual, entre pósters | mueve el cursor |
| `↓` `↑` | tarjetas: ± una fila; lista: ±1 | ± una fila de pósters | tarjetas: ± una fila; lista: ±1 |
| Enter | abre el original (el "Abrir original" del panel) en otra pestaña, con el toast "Abriendo {dominio}…" | abre el link de la ficha ("Abrir en …") igual | abre la pantalla de la idea |
| `f` | ★ del panel (como clic) | nada (Ocio no tiene Favoritos) | nada |
| `e` | foco en "+ etiqueta" del panel | foco en "+ etiqueta" del panel | nada |
| `x` | marca/desmarca el elegido | igual | marca/desmarca la del cursor |
| Backspace/Delete | borra los marcados, con Deshacer | igual | igual |
| `v` | alterna Lista / Tarjetas | nada (sólo pósters) | alterna Lista / Tarjetas (la lista de Ideas tiene las dos) |

- **Una fila** son las columnas que se ven: los ítems cuyo `offsetTop` es el
  del primero. Sin ítem elegido, cualquier movimiento elige el primero. Las
  flechas hacen `preventDefault` (no scrollean la columna) y el elegido se
  lleva a la vista con `scrollIntoView({block: "nearest"})`.
- Las tarjetas "Analizando…" se recorren pero no se marcan con `x`.
- El cursor de la lista de Ideas es la clase `on` del ítem, guardada en
  `#items[data-current]`, como en las otras listas. Clic sigue abriendo.
- `v` hace clic en el `a[data-view]` que no está activo. Ocio no tiene ninguno:
  ahí no pasa nada sin regla aparte.

**Pantalla de una idea** (`/ideas/{id}`): sólo las globales. `/` va al
buscador "Buscá en tus N links para sumar".

**Hints en la barra lateral.** Cada sección lleva a la derecha, después del
contador, `<kbd class="key mono js-only">1</kbd>` (2, 3), con el estilo del
README. El `<kbd>/</kbd>` del campo unificado deja de ser decorativo.

## 5. Selección múltiple

**Checkbox.** En cada ítem marcable, fuera del `<a class="hit">` (un input no
puede ir dentro de un link):

```html
<label class="check js-only"><input type="checkbox" name="ids" value="{id}"
       form="bulk" aria-label="Seleccionar {título}"></label>
```

- `shelf-items.html` (tarjeta y fila de la Biblioteca; las "Analizando…" no
  lo llevan), `posters.html`, `idea-items.html`.
- Tarjeta y póster: 18px arriba a la izquierda, radius 5, borde
  `1.5px #55575f`; marcado: bg y borde `#e7e7ea` con ✓. En el póster el chip de
  tipo se corre a la derecha del checkbox. Fila: la primera columna de
  `18px 8px 1fr auto`.
- Es un elemento aparte del link, así que el clic no abre el detalle.
- Sin JS no se ve (`.js-only`), y la grilla de la fila vuelve a tres columnas.

**Barra.** `bulk-bar.html`, incluida por `home.html`, `ocio-shelf.html` e
`idea-shelf.html` en la columna central:

```html
<form id="bulk" class="bulk" method="post" hidden> …
```

Flotante abajo al centro (medidas y colores del README). Contenido:
- "N seleccionados" ("1 seleccionado").
- **Mover a ▾**: un `details.menu.up` con botones
  `formaction="/bulk/<acción>" name="<campo>" value="…"`:
  - Biblioteca: las categorías (punto + nombre) y un input "Nueva categoría"
    (Enter). Acción `category`.
  - Ocio: los tipos (`cards.KINDS`, con sus nombres). Acción `kind`.
  - Ideas: semilla, en marcha, hecha, descartada. Acción `state`.
- **★ Favorito** (sólo Biblioteca): `formaction="/bulk/mark"`, `mark=⭐`.
- **Borrar** (`#e59a8f`): `formaction="/bulk/delete"`.
- **✕**: limpia la selección.

Los checkboxes son parte del formulario por `form="bulk"`, así que
`FormData(bulk)` ya trae los `ids`.

**`select.js`:**
- Muestra la barra con ≥1 marcado y actualiza el número.
- Manda la barra con `fetch` y `Accept: application/json`. Al volver: toast
  (con Deshacer si trae `undo`), limpia la selección y recarga la lista
  (`oknowledge.list.reload()`) y el panel si el elegido cambió o se borró.
- Sobrevive a las recargas de la lista: `shell.js` dispara en `#list` el evento
  `oknowledge:list` con `detail.reason` = `"filter"` (filtro, búsqueda, orden,
  vista), `"refresh"` (recarga de la misma lista) o `"more"`. Con `filter`
  limpia; con los otros vuelve a marcar los ids que siguen en pantalla y olvida
  los que ya no están. Cambiar de sección es otra página: arranca vacía.
- Esc limpia (cuando no había menú ni foco en un campo, §4).

### 5.1 Rutas en lote

`POST /bulk/{action}`, `action` ∈ `category`, `kind`, `state`, `mark`,
`delete`. Otra cosa da 404.

| action | Campos | Para cada id hace | Vale en |
|---|---|---|---|
| `category` | `ids`, `category` | lo de `POST /item/{id}/category` | links |
| `kind` | `ids`, `kind` | lo de `POST /item/{id}/kind` | fichas |
| `state` | `ids`, `state` | lo de `POST /item/{id}/mine/state` | ideas (y fichas) |
| `mark` | `ids`, `mark` | lo de `POST /item/{id}/mark`; ⭐ con la regla de "¿★ Favorito en lote?" | links |
| `delete` | `ids` | lo de `POST /item/{id}/delete` | links, fichas, ideas |

- **Una sola regla.** El cuerpo de cada ruta de un ítem pasa a una función
  (`move_one`, `retype_one`, `restate_one`, `mark_one`, `delete_one`) que
  devuelve el `Edited` de hoy. La ruta de un ítem y la de lote llaman a la
  misma. Los chequeos (`clean_category`, `cards.KINDS`, `states_for`,
  `clean_mark`) se hacen una vez, antes del primer id: un valor rechazado da
  400 con el error de hoy y no escribe nada.
- **Un solo rebuild.** `update_note()` y `delete_note()` reciben
  `rebuild: bool = True`. En lote se llaman con `False` y al final se corre
  `rebuild_indexes()` una vez por estante tocado; si falla, el aviso suma el
  texto de `indexes-stale`. Cada nota se sigue escribiendo bajo su lock, como
  en `edit()`.
- Un id que no existe, que está en otro estante que el de la acción, o con un
  análisis corriendo (`busy`), se saltea y cuenta como no hecho.

**JSON** (las rutas de lote arman el texto con `t()`, porque lleva nombres):

```json
{"ok": true, "notice": "3 movidos a Redes", "done": ["id1", "id2", "id3"],
 "failed": ["id4"], "undo": "<token>"}
```

- `undo` sólo en `delete`.
- Textos: "%1 movidos a %2" / "1 movido a %2"; "%1 marcados como favoritos" /
  "Se quitó favorito a %1"; "%1 borrados" / "Borrado". Si hubo `failed`, se
  agrega " · %1 no se pudieron cambiar".
- Ninguno hecho: `{"ok": false, "error": "…"}` con el estado de la primera
  falla (`busy` 409, `write-failed` 500; todos inexistentes: 404 `GONE`).
- Sin `Accept: application/json` (no pasa: sin JS no hay checkboxes)
  redirige a `back` (`local_path`) o a la sección, con `notice=saved`.

## 6. Borrar y Deshacer

### 6.1 Qué toca hoy un borrado

`delete_note()` mueve el `.md` a `<vault>/oknowledge/trash/` (con nombre libre
si choca) y reconstruye los índices de su estante. Nada más:
- **Portada** (`attachments/`): no se toca. Al restaurar, la nota la vuelve a
  encontrar.
- **Links de una idea**: una idea que vinculaba un link borrado lo sigue
  nombrando ("ya no está", atenuado). Al restaurar el link, el vínculo vuelve
  solo. Borrar una idea no toca los links.
- **Cola** (`Queue`): no se toca. Un link con su entrada en `pending` o
  `error` sigue contando en "esperando análisis", y un "Analizar" puede volver
  a crear la nota. Es lo de hoy y no cambia en esta entrega.
- Un link con un análisis corriendo no se borra (`busy`), como hoy.

Deshacer devuelve el archivo, con todo su frontmatter (categoría, etiquetas,
marca, colecciones, estado, estrellas, nota, vínculos), a su ruta original, y
reconstruye los índices. No hay nada más que restaurar.

### 6.2 Lotes

Módulo nuevo `src/oknowledge/undo.py`:

- `remember(items) -> str`: escribe
  `state_dir()/undo/<token>.json` (con `atomic_write`):
  `{"at": "<ISO UTC>", "items": [{"id", "shelf", "source", "target"}]}`.
  `source` y `target` son rutas relativas a `cfg.root`; `shelf` es `links`,
  `ocio` o `ideas`. El token es `secrets.token_urlsafe(16)` (22 caracteres
  `[A-Za-z0-9_-]`). Antes de escribir, purga los vencidos.
- `restore(cfg, token, language, lock) -> UndoResult | None`: `None` si el token
  no tiene esa forma, no existe o tiene más de 24 h. Para cada ítem, bajo
  `lock(id)`, llama a `vault.restore_note()`. Al final corre un rebuild por
  estante tocado y borra el JSON. Devuelve `restored` y `skipped` (ids).
- `purge(now=None)`: borra los JSON de más de 24 h. Sólo JSON, nunca una nota.
  Se llama al crear la app (`create_app`, envuelto en `try/except OSError` con
  log) y desde `remember()`.
- La hora es `datetime.datetime.now(datetime.timezone.utc)`, nunca `utcnow()`.

En `vault.py`:
- `delete_note()` devuelve `Trashed(source: Path, target: Path)` en vez del
  `Path` del destino. `IndexesStale.done` lleva lo mismo. Su único llamador es
  `app.py`.
- `restore_note(cfg, link_id, source, target, language, shelf, rebuild=True)
  -> bool`. Devuelve `False`, sin tocar nada, si:
  - `target` no está dentro de `trash_dir(cfg)` o `source` no está dentro de
    `shelf.dir` (`ensure_inside_root`);
  - `target` ya no existe, no tiene `oknowledge: 1` o su `id` no es `link_id`;
  - `source` ya existe, o el estante ya tiene otra nota con ese id (el link se
    volvió a pegar mientras tanto).

  Si pasa, mueve el archivo sin pisar nada (`os.link` + `unlink`; si `os.link`
  falla porque el destino apareció, no se mueve) y reconstruye.

En `app.py`, `Edited` suma `value` (lo que devolvió el cambio), para que la
ruta lea el `Trashed`.

### 6.3 Rutas

`POST /item/{id}/delete` (sin cambios de regla). Si aterrizó, guarda un lote
con ese ítem y contesta:
- JSON: `{"ok": true, "notice": "Borrado", "undo": "<token>"}`. Con JSON la
  ruta usa la clave nueva `deleted` de `NOTICES`; el texto largo de `trashed`
  queda para la redirección (`trashed-indexes-stale` se mantiene en los dos);
- redirección: la de hoy (`/`, `/ocio` o `/ideas`) con
  `notice=trashed&undo=<token>`. Ahí el toast del servidor ofrece Deshacer
  (§2).

`answer()` copia a la JSON los parámetros `undo` y `reload` cuando vienen; en la
redirección van a la URL como cualquier otro.

`POST /undo/{token}`, campo `back` (opcional, pasa por `local_path`):
- JSON `{"ok": true, "notice": "Restaurado" | "%1 restaurados", "restored":
  [...], "skipped": [...]}`. Con `skipped` no vacío el aviso suma " · %1 no:
  ya hay otra nota con ese link";
- token inválido, inexistente o vencido: `undo-gone` ("Ya no se puede
  deshacer"), 404 en `FAILURES`;
- todos salteados: `undo-blocked` ("No se pudo restaurar: ya hay otra nota con
  ese link"), 409;
- sin JSON: 303 a `back` (o a la sección del primer ítem) con el aviso.

### 6.4 En pantalla

- **Panel de un link**: el Borrar del ⋯ pasa a `data-inline` y pierde el
  `confirm()`. **Ficha**: pierde el `confirm()` (ya era inline). `shell.js`, al
  volver con `undo`, muestra el toast con Deshacer, recarga la lista y abre el
  que seguía (§Decisiones). Deshacer: `POST /undo/{token}` como JSON; si
  restauró, recarga la lista y abre el primer id restaurado.
- **Pantalla de una idea**: el "Borrar idea" del ⋯ pierde el `confirm()` y
  sigue siendo un formulario común. Redirige a `/ideas?notice=trashed&undo=…`,
  y el toast del servidor ofrece Deshacer. Con JS, `app.js` lo manda como JSON y
  recarga la lista.
- **En lote**: §5.
- Un toast nuevo antes de los 5 s se lleva el Deshacer. El lote sigue en disco
  24 h; no hay otra forma de usarlo desde la interfaz.

## 7. Barra lateral

- Pie: **Atajos** `<kbd>?</kbd>` (botón `js-only`, abre §3.2) y **Ajustes**
  (`/settings`, con JS abre §3.1). "Ajustes" lleva el contador de un lote que
  corre (`3/10`) o de los links ocupados, como hoy "Actividad".
- Se van "Categorías" y "Actividad".
- Hints `1` `2` `3` en las secciones (§4).

## 8. Sin JavaScript

- Ajustes es la página `/settings?tab=…`, con pestañas que recargan y un botón
  Guardar por formulario. Categorías está ahí; `/categories` redirige.
- Importar, Actividad y la vista previa de WhatsApp: las páginas de hoy.
- No hay atajos, ni ayuda, ni checkboxes, ni barra flotante: no se dibujan.
- Borrar redirige a la sección con el toast del servidor y su Deshacer, que es
  un formulario. Pasados los 5 s, la nota sigue en `trash/` del vault, como
  dice el aviso.

## 9. Pendientes de entregas anteriores que entran

De `2026-10-14-rediseno-biblioteca-pendientes.md` y
`2026-10-14-rediseno-ocio-ideas-pendientes.md`, porque tocan `shell.js` o el
toast:

- El `.catch` de `loadList` navega sólo si el pedido sigue siendo el último
  (`mine === asked`).
- Una tanda de "más" que vuelve después de que la lista cambió se descarta (el
  mismo contador `asked`).
- El poller deja de preguntar por un id que ya no está en la lista ni en el
  panel (`clearInterval` cuando el elemento no está conectado).
- Un clic en un filtro cancela el temporizador de 250 ms de la búsqueda.
- Un link de orden fuera de la barra lateral no borra el resaltado de la
  barra (`setActive` sólo limpia si el link está en `.sidebar`).
- "+ etiqueta": `required` en el panel del link, para que Enter vacío no
  postee. Después de sumar una, el foco vuelve al campo, en el panel
  (`id="tag-add"`, que `loadPanel` ya sabe reenfocar) y en la pantalla de una
  idea (`idea.js`, después de reemplazar `idea-tags`). Es lo que necesita `e`
  para sumar varias seguidas.
- Un solo `toast()` (antes había uno en `shell.js` y otro en `autosave.js`).

## 10. Textos

Claves en inglés y castellano en `i18n.py`, como en las entregas anteriores.
Los del handoff van tal cual, entre otros: "Ajustes", "Los cambios se guardan
solos", "Motores", "Idioma y guardado", "Importar", "Categorías", "Buscar
modelos", "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos
separados por coma.", "¿Dónde se guarda esto?", "Idioma de los resúmenes",
"Idioma de la interfaz", "Compartido con tus otros plugins de Omarchy",
"Cambiarlo recarga la página", "Guardar por defecto", "Lo que se marca al pegar
un link", "Menciones de un video", "Links a analizar por vez", "Cuántos procesa
cada tanda", "Soltá acá el export de WhatsApp", "Elegir archivo", "Links
esperando análisis: %1", "Analizar %1 links", "Analizando %1 links", "Ver
actividad", "Si renombrás a una que ya existe, se unen.", "¿Unir «%1» con
«%2»?", "Atajos", "Atajos de teclado", los once textos de §3.2, "%1
seleccionados", "1 seleccionado", "Mover a", "Nueva categoría", "%1 movidos a
%2", "1 movido a %2", "%1 marcados como favoritos", "Se quitó favorito a %1",
"%1 borrados", "Borrado", "%1 no se pudieron cambiar", "Deshacer",
"Restaurado", "%1 restaurados", "Ya no se puede deshacer", "No se pudo
restaurar: ya hay otra nota con ese link", "Abriendo %1…", "Seleccionar %1".

## 11. Pruebas

- **Vault**: `delete_note` devuelve `Trashed`; `restore_note` devuelve la nota
  a su ruta y reconstruye; no restaura si `source` existe, si hay otra nota con
  el id, si el archivo de `trash/` perdió el marcador o cambió de id, ni rutas
  fuera de `trash/` o del estante; `rebuild=False` no reconstruye (en
  `update_note` y `delete_note`).
- **`undo.py`**: el JSON cae bajo `$XDG_STATE_HOME/oknowledge/undo/` (el de
  `conftest.py`); `restore` con un token vencido (un `now` falso) da `None`;
  `purge` borra sólo JSON vencidos y nunca un `.md`; tokens con `/`, `..` o de
  otro largo se rechazan sin tocar el disco.
- **Borrar**: `POST /item/{id}/delete` de link, ficha e idea, con JSON (trae
  `undo`) y sin JSON (la URL trae `undo=`); la página con `?undo=` vigente
  dibuja el toast con el formulario Deshacer y con uno inventado no.
- **Deshacer**: `/undo/{token}` con JSON y sin JSON; la nota vuelve a `/lista`,
  `/ocio/lista` e `/ideas/lista`, con su portada y su vínculo desde una idea;
  un segundo Deshacer da 404; un link vuelto a pegar en el medio queda en
  `skipped` (409 si era el único).
- **Lote**: cada acción con dos o tres ids; un id inexistente y uno de otro
  estante quedan en `failed`; un valor rechazado (categoría inválida, tipo o
  estado desconocido) da 400 sin escribir nada; un solo rebuild por estante
  (contado con monkeypatch); la regla de ★ (todos ⭐ → se quita; mezcla → se
  pone); `delete` en lote devuelve un token que restaura todos; los textos de
  `notice`.
- **Ajustes**: `/settings/panel` es un fragmento con las cuatro pestañas y
  `tab=` elige cuál se ve (desconocido = motores); `/settings?tab=` igual en
  página; `POST /settings` con sólo los campos de una pestaña no cambia los de
  otra (los modelos no se borran); JSON con `reload` sólo si cambia
  `ui_language`; `settings-failed` en JSON es 500; `/settings/models/{engine}`,
  `/settings/env`, `/retry` y `/categories/rename` contestan JSON; `/categories`
  redirige.
- **Barra lateral**: el pie tiene Atajos y Ajustes (y el contador del lote) y
  no tiene Categorías ni Actividad; los `kbd` 1/2/3; `/retry` sigue
  respondiendo y el fragmento de Importar lo enlaza.
- **Markup**: el `<dialog>` de Atajos con sus once filas está en `base.html`;
  los checkboxes son `js-only`, van fuera del `a.hit` y tienen `form="bulk"`;
  las "Analizando…" no tienen; la barra de lote de cada sección trae sus
  opciones de Mover a, y ★ sólo en la Biblioteca.
- **JS**: los tests de texto de siempre (que `app.js` y `select.js` se sirvan y
  que `shell.js`/`autosave.js` ya no definan su toast), más una pasada con
  Playwright sobre un vault de prueba: cada tecla de §4 en las tres listas y en
  la pantalla de una idea; las teclas ignoradas dentro de un campo y con Ctrl;
  marcar, mover, ★, borrar y Deshacer en lote; la selección que sobrevive al
  poller y se limpia al filtrar; un menú que cierra a otro y Esc, también en la
  pantalla de una idea; autoguardado de cada pestaña de Ajustes, el idioma que
  recarga, el renombre que pide confirmar al unir.
- Capturas a 1440×900 comparadas con `03`, `07`, `08` y `09`. El vault real y
  `~/.config/oknowledge` no se tocan.

## Fuera de alcance

- Celular (entrega 4).
- Restaurar desde la interfaz pasados los 5 s del toast, o una papelera
  navegable.
- Selección con Shift (rangos) y seleccionar todo.
- Que borrar un link limpie su entrada de la cola.
- Colecciones y otras marcas en lote.
- El resto de los pendientes de las entregas 1 y 2.

Después del merge en `main`, el cambio se lleva a la rama `windows` del fork
como los anteriores.
