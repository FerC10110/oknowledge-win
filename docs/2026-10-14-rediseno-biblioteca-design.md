# Rediseño, entrega 1: la base y la Biblioteca

**Fecha:** 2026-10-14 · **Rama:** `feat/rediseno-biblioteca`
**Referencia visual:** `design_handoff_oknowledge_redesign/` (README, `oknowledge App.dc.html`,
`screenshots/`). Colores, tipografía y espaciado de ese handoff son finales: este
documento dice *qué* se construye y *cómo* encaja en oknowledge; los números
exactos (px, colores, radios) salen del README del handoff.

> "Implementá el rediseño descrito en design_handoff_oknowledge_redesign/README.md"

El rediseño completo se parte en cuatro entregas, cada una con spec, plan y
merge propios, y la app funcionando al final de cada una:

1. **Base + Biblioteca** (este documento).
2. Ocio e Ideas en el mismo esquema (pestañas Idea / Links vinculados).
3. Ajustes y ayuda como modales, selección múltiple, toast con Deshacer, atajos.
4. Celular.

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Cómo se construye? | Servidor arma la página (FastAPI + Jinja, como hoy); JavaScript chico cambia columnas sin recargar. Sin build ni framework |
| ¿Estado? | En la URL: recargar o compartir deja en el mismo lugar |
| ¿Marcas? | ★ (= la marca ⭐) con botón; 📌 Fijados y las demás marcas en uso como filtros en la barra lateral; ponerlas desde el menú ⋯ |
| ¿Colecciones? | Grupo COLECCIONES en la barra lateral; "Agregar a colección" en el menú ⋯; sus chips con × en el panel |
| ¿Tema? | Sólo oscuro, el del handoff. Se va el modo claro |
| ¿Fuente? | Geist y Geist Mono como `.woff2` dentro de `static/` (OFL), sin pedir nada afuera |
| ¿Paginación? | No: la columna carga de a 60 y suma más al llegar al final |
| ¿Tira de etiquetas y filtro año/mes? | Se van. Tocar un `#tag` del panel filtra por esa etiqueta |
| ¿Modo "Seleccionar" (colecciones en lote)? | Se va en esta entrega; vuelve como selección múltiple en la 3 |

## 1. Estructura y URLs

`/` es la pantalla fija de tres columnas del handoff (`216px minmax(0,1fr) 480px`,
`height:100vh`, `grid-template-rows:minmax(0,1fr)`, sin scroll del `body`; sólo
scrollean las áreas internas).

Parámetros de `/` (todos opcionales, combinables como hoy):

| Parámetro | Qué hace |
|---|---|
| `cat` | filtra por categoría |
| `tag` | filtra por etiqueta |
| `mark` | filtra por marca (`⭐`, `📌`, …) |
| `col` | filtra por colección |
| `q` | busca (la búsqueda de hoy, `Library.search`); con `q` los demás filtros se ignoran, como hoy `/search` |
| `sel` | id del link abierto en el panel. Si falta o no está en la lista, se abre el primero visible |
| `vista` | `tarjetas` (por defecto) o `lista` |

Los nombres viejos (`category`, `tag`, `collection`) siguen aceptados para no
romper links guardados; `/search?q=` y `/marked?mark=` redirigen a `/` con el
parámetro equivalente.

**Fragmentos** (mismo patrón que `/item/{id}/buscar-links`):

- `GET /lista?<los mismos parámetros>&desde=N` → la columna central (cabecera +
  tarjetas o filas). Con `desde` devuelve sólo los siguientes 60 ítems, para la
  carga al llegar al final.
- `GET /panel/{id}` → el panel de detalle de un link. 404 si no existe.

Con JavaScript, un clic en filtro, tarjeta o vista pide el fragmento, lo pone en
su columna y actualiza la URL con `history.replaceState`. Sin JavaScript todo es
un `<a href>` a `/?…` que recarga la página y muestra lo mismo.

`GET /item/{id}` de un link redirige (303) a `/?sel={id}`. Así siguen andando
los links viejos, los de Obsidian y las redirecciones de todas las rutas que
escriben (`see_other(item_url(id), notice=…)`). Ocio e Ideas mantienen su
`/item/{id}` hasta la entrega 2.

**Páginas que todavía no se rediseñan** (Ocio, Ideas, ficha de Ocio, idea,
Ajustes, Importar, Categorías, Actividad, candidatos de Ocio, 404): se dibujan
dentro de la nueva estructura — barra lateral a la izquierda y su contenido de
hoy en una columna que scrollea — con los tokens oscuros y Geist. No cambian de
comportamiento.

## 2. Tokens y tipografía

- Las variables de `:root` pasan a ser los tokens del handoff (fondo `#141519`,
  superficies, bordes, textos, acento `#a9b4de`, favorito `#d9b54a`, destructivo
  `#e59a8f`, primario). Se elimina el bloque `prefers-color-scheme`. Las reglas
  existentes que usan `--bg`, `--fg`, `--dim`, `--line`, `--accent`, `--card`
  siguen funcionando: esos nombres se mapean a los tokens nuevos.
- `@font-face` para Geist 400/500/600 y Geist Mono 400/500 desde
  `/static/fonts/`, con `font-display: swap`. Se incluye el texto de la licencia
  OFL junto a los archivos.
- Color de categoría: punto `oklch(0.74 0.09 H)`, miniatura de respaldo
  `oklch(0.30 0.045 H)`. Hues fijos para las del handoff (Productividad 80,
  Programación 160, Redes 265, Salud 25); cualquier otra categoría recibe un hue
  derivado de su nombre (estable entre cargas). "Sin categoría" usa `#6d6f78` /
  `#24252b`. El cálculo vive en Python (un filtro o función de plantilla), no en
  JavaScript.

## 3. Barra lateral

En este orden, con las medidas del handoff:

1. Logo "oknowledge".
2. Secciones: Biblioteca, Ocio, Ideas, cada una con su contador. La activa
   resaltada. (Las teclas 1/2/3 llegan en la entrega 3; el hint de tecla no se
   dibuja hasta entonces.)
3. **CATEGORÍAS**: Todo, cada categoría (punto de color + nombre + contador),
   ★ Favoritos (`mark=⭐`).
4. **MARCAS**: 📌 Fijados y, debajo, cada otra marca con al menos una nota en la
   Biblioteca, con su contador. Si no hay ninguna aparte de ⭐, el grupo muestra
   sólo 📌 Fijados (con 0).
5. **COLECCIONES**: cada colección con su contador. Sin colecciones, el grupo no
   se dibuja.
6. Pie: "Categorías", "Actividad" y "Ajustes", links a sus páginas de hoy.
   En la entrega 3 los dos primeros pasan adentro de Ajustes y entra "Atajos ?".

El filtro activo se resalta. En las páginas que todavía no se rediseñan la
barra lateral muestra sólo logo, secciones y pie.

## 4. Columna central

**Campo unificado** (arriba). Un `<form method="get" action="/">` con un input
`name="q"`:

- Texto común: con JavaScript filtra en vivo (250 ms sin escribir, se descarta
  la respuesta de una búsqueda vieja, como `idea-links.js`); sin JavaScript,
  Enter busca.
- Si empieza con `http://`, `https://` o `www.`: no filtra, y aparecen el
  segmentado **Completo | Resumen** (por defecto el de Ajustes,
  `default_content`) y **Guardar ↵**. Enter guarda. Ver §6.
- Vacío: el hint `/` a la derecha (decorativo hasta la entrega 3).
- Placeholder: "Buscá o pegá un link para guardarlo".

**Cabecera**: "{filtro o Biblioteca} · {n}" y el segmentado **Lista | Tarjetas**.
La vista elegida se recuerda en `localStorage` (envuelto en try/catch) y viaja
en la URL como `vista`.

**Tarjetas** (por defecto): grilla de 3 columnas del handoff. Miniatura de 92px
con la portada de hoy (`/cover/{id}`) o, si no hay portada, el bloque de color
de la categoría; chip con el dominio abajo a la izquierda; ★ arriba a la derecha
si tiene ⭐ (otra marca se muestra en su lugar). Título a dos líneas, punto +
"Categoría · fecha corta". La seleccionada con borde `#565a6a`. Sin checkbox en
esta entrega.

**Lista**: filas del handoff sin checkbox: punto · título y subtítulo · fecha
corta en Mono.

**Carga**: los primeros 60 ítems vienen con la página; al acercarse al final
(IntersectionObserver sobre un centinela) se piden los siguientes con
`/lista?…&desde=N`. Sin JavaScript, el centinela es un link "Ver más" a
`/?…&hasta=N+60` que dibuja los primeros N+60.

**Estados vacíos** (centrados):

- Búsqueda sin resultados: "Nada coincide con “{q}”" + "Probá con otra palabra
  o una etiqueta. Si es un link nuevo, pegalo completo con https:// para
  guardarlo."
- Filtro vacío: "No hay nada en {filtro}" + una pista.
- Biblioteca vacía: el texto de bienvenida de hoy.
- Los dos primeros con botón "Ver todo" (`/`).

**Errores del vault** (índice ilegible, vault inexistente): el mismo mensaje de
hoy, en la columna central.

## 5. Panel de detalle (link)

Contenido scrolleable + barra de acciones fija abajo.

- **Fila meta**: chip "● Categoría ▾" (un `<details>` con menú): las categorías
  existentes como botones, más un campo "Nueva categoría". Elegir una hace POST a
  `/item/{id}/category`. Después: "dominio · fecha".
- **Título** (26px) y "N min de lectura del resumen" (palabras del resumen /
  200, mínimo 1).
- **Resumen** en párrafos.
- **EN TRES LÍNEAS**: los puntos clave (todos los que haya). Sin puntos, no se
  dibuja el recuadro.
- **Menciones**, si hay, con × (`/item/{id}/mentions/delete`).
- **Contenido original**, desplegable, si hay.
- **Colecciones** a las que pertenece, como chips con × (`/item/{id}/collections`,
  `drop`).
- **Etiquetas**: chips `#tag` (link a `/?tag=…`) con × y un input "+ etiqueta"
  (Enter agrega). Ambos hacen POST a `/item/{id}/tags` con la lista completa
  resultante.
- **Incompleto**: si `status != ok`, el aviso de hoy.
- **Analizando**: si el link está en la cola (pendiente o con lock), el panel
  muestra título provisorio (la URL), "La IA está leyendo el link…" en
  `#a9b4de` y tres barras esqueleto, sin el resto.

**Barra de acciones**:

- **Abrir original ↵** (primario, `<a>` a la URL).
- **A una idea ▾**: menú con las ideas no descartadas; elegir una hace POST a
  `/item/{id}/ideas` (`back` = la URL actual). Sin ideas, el botón no aparece.
- **★** (`margin-left:auto`): POST a `/item/{id}/mark` con `⭐`, o con vacío si ya
  la tiene (sacar la marca). Activo en `#d9b54a`.
- **⋯**: menú con
  - las marcas (las 12 de `cfg.marks`, la actual resaltada, y "Sin marca"),
  - "Agregar a colección" (input + colecciones existentes; POST a
    `/item/{id}/collections`, `add`),
  - "Reprocesar con IA" (POST a `/item/{id}/reprocess` con la cadena por
    defecto, previa confirmación con el texto de hoy),
  - "Borrar" en `#e59a8f` (POST a `/item/{id}/delete`, previa confirmación con
    el texto de hoy).

Los menús son `<details>`: andan sin JavaScript; con JavaScript se cierra uno al
abrir otro y con Esc.

Todo lo que se va de la página de un link: "Mover a categoría" con 💾, "Editar
etiquetas" con 💾, el select de motor al reprocesar, el botón "Borrar" suelto, el
formulario "Agregar a una idea" con select.

## 6. Guardar un link

**Guardar ↵** hace POST a `/add` (`url`, `content`), igual que hoy; la ruta
redirige a `/?sel={id}&notice=reading` en vez de `/?notice=reading` (el id es
`link_id(clean)`, conocido antes del análisis).

**Lo que está en la cola** se lista arriba de todo en la columna central, antes
de las notas, como tarjetas "Analizando…": miniatura gris, título = la URL,
subtítulo "Analizando…" en `#a9b4de`, categoría "Sin categoría". Salen de la
cola (`Queue`) y no del vault: las pendientes y las con lock. Un link en la cola
que ya tiene nota (reproceso) no se duplica: su tarjeta normal se dibuja con el
subtítulo "Analizando…". Las fallidas no se listan (siguen en Actividad).

**Seguimiento**: con JavaScript, cada tarjeta "Analizando…" pregunta cada 3 s a
`/item/{id}/state`. Cuando `working` pasa a falso, se recarga la columna
central (y el panel si es la seleccionada) y aparece el toast "Listo: resumen
generado"; si el estado es `failed`, el toast dice "No se pudo analizar el link"
y la tarjeta desaparece de la cola. Sin JavaScript, recargar muestra el estado.

Las cosas de Ocio pegadas en el campo (`película:…`, IMDb, Goodreads) siguen el
camino de hoy: `/add` las manda a la ficha o a los candidatos de Ocio.

## 7. Autoguardado y toast

Con JavaScript, los formularios del panel marcados `data-inline` se envían con
`fetch` (mismo origen: el chequeo de `Origin` pasa). Al volver:

- se recarga el panel (`/panel/{id}`) y, si cambió algo visible en la lista
  (categoría, marca, título), la columna central;
- si la URL final de la respuesta trae `notice`, se muestra como **toast**
  (arriba al centro, `#e7e7ea` sobre `#141519`, 2,2 s) con el mismo texto que hoy
  usa el aviso;
- un error de red o un 4xx/5xx muestra el toast "No se pudo guardar".

Borrar no es inline: navega a `/` como hoy. Los avisos que hoy aparecen arriba de
la página, en `/` se dibujan como toast también sin JavaScript (el servidor lo
pone en la página y el CSS lo oculta a los 2,2 s con una animación).

Sin JavaScript, todos son formularios comunes que recargan.

## 8. Textos

Todos los textos nuevos pasan por `t()` con clave en inglés y traducción en
`i18n.py` (es), como hoy. Los textos del handoff son la versión en español.

## 9. Pruebas

- `/` con cada filtro (`cat`, `tag`, `mark`, `col`, `q`) muestra lo que
  corresponde, la cabecera con el conteo, y los nombres viejos siguen andando.
- `sel` abre ese link en el panel; uno inexistente o filtrado abre el primero.
- `/lista` y `/panel/{id}` devuelven fragmentos sin `<html>`; `/panel/` de un id
  inexistente da 404; `desde` corta en 60.
- `/item/{id}` de un link redirige a `/?sel=`; de una ficha de Ocio o una idea,
  sigue mostrando la página.
- `/search` y `/marked` redirigen.
- La barra lateral: categorías con contador, ★ Favoritos, 📌 y marcas en uso,
  colecciones; el color de categoría es estable y el de las conocidas es el del
  handoff.
- Los ítems de la cola aparecen como "Analizando…" arriba y no duplican una nota
  existente; `/add` redirige con `sel`.
- El panel: chip de categoría con menú, puntos, menciones, colecciones,
  etiquetas con ×, ★ activa, menú ⋯ con marcas/colección/reprocesar/borrar,
  "A una idea" sólo con ideas.
- Las páginas no rediseñadas siguen respondiendo y llevan la barra lateral.
- Los tests existentes que miran markup viejo se ajustan; los de rutas que
  escriben no cambian salvo la redirección de `/item/{id}`.
- Capturas a 1440×900 con el vault de prueba, comparadas con
  `screenshots/01` y `02` del handoff.

## Fuera de alcance (entregas siguientes)

- Ocio e Ideas con panel (entrega 2).
- Ajustes y atajos como modales, teclado, selección múltiple, barra flotante,
  Deshacer (entrega 3).
- Celular (entrega 4). En esta entrega, por debajo de ~60rem la pantalla cae a
  una columna que scrollea (barra lateral arriba, lista, panel), sin pulir.
- Página de Categorías (renombrar) y Actividad: siguen como páginas, con link
  desde el pie de la barra lateral.

Después del merge en `main`, el cambio se lleva a la rama `windows` del fork
como los anteriores.
