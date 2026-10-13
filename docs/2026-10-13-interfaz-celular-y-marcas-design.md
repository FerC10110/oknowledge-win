# La interfaz en el celular, y marcas con emoji

**Fecha:** 2026-10-13 · **Rama:** `feat/mobile-and-marks`

La web se usa cada vez más desde el celular, y ahí se nota lo que en el
escritorio pasa desapercibido. El pedido:

> "se debe ver bien en el celular y ser practico, los anios al hacer click
> deben aparecer los meses con nombre reducido [...] las categorias deben estar
> todas colapsadas en el celular. Quiero poder marcar las tarjetas con un emoji
> (se debe mostrar un listado) y los emojis usados aparecen como filtro a la
> derecha de Ajustes. dentro de categories que no sean filas, se desperdicia
> mucho lugar. Quiero que revises todas las paginas y busques mejoras de
> usabilidad"

Dos cosas en una rama: una marca tuya por tarjeta, que es lógica nueva, y un
repaso de todas las páginas a ancho de celular, que es casi todo CSS.

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Cuántos emojis por tarjeta? | uno; tocar otro lo reemplaza, tocar el mismo lo saca |
| ¿Qué lista ofrece el selector? | una lista fija y corta, más un campo "otro" para pegar cualquiera |
| ¿Qué muestra el filtro del nav? | todo lo marcado con ese emoji: links, fichas e ideas, en una grilla |
| ¿Dónde se elige? | en la esquina de cada tarjeta y en la página de la nota |
| ¿En qué estanterías? | las tres: links, ocio, ideas |
| ¿Dónde empieza "celular"? | por debajo de 42rem, el corte que el CSS ya usa |

## Hechos medidos

Capturas de chromium headless a 390px y 1366px contra un vault de prueba (70
links en cuatro años, 6 fichas, 3 ideas), sobre main 840f018:

1. `.actions { opacity: 0 }` sólo se muestra con hover (`style.css:241`). En
   un celular no hay hover: en **Categorías** los campos de renombrar no se ven
   y cada fila es un hueco de ~140px; en la **página de un link** no se ven
   mover de categoría, etiquetas ni borrar.
2. Las tarjetas miden 21rem fijos (`style.css:149`). Sin portada queda un hueco
   de ~120px por tarjeta; en una sola columna, media pantalla vacía por nota.
3. La cabecera ocupa ~210px en el celular, en todas las páginas, y el
   `autofocus` de la búsqueda abre el teclado al entrar.
4. Los meses ya son cortos (`MONTHS` en `app.py:187`, "ene", "feb"... en
   `i18n.py`), pero en el celular la línea de tiempo es una fila con scroll
   horizontal y los meses se agregan *después* de los años, fuera de la
   pantalla: tocar 2025 parece no hacer nada.
5. Categorías, colecciones y etiquetas ocupan ~330px antes de la primera
   tarjeta.
6. "Todo" es dos cosas: el botón de la cabecera (guardar el contenido completo)
   y el chip de categorías (todas).
7. Menores: estrellas de ~20px, "Seleccionar" solo en una línea en el
   escritorio, motores en Ajustes en tres bloques altos, el aviso de notas
   ilegibles con la ruta completa.

## 1. Marcas con emoji

### Dato

Un campo nuevo en el frontmatter, `mark`, con un emoji o ausente. Es tuyo
como `state`, `score` y `my_note`: ningún modelo lo escribe. `Note.mark: str =
""`; `render()` lo escribe sólo si no está vacío; `read_note()` lo lee con el
mismo criterio que `_as_text`.

### Sobrevivir a las reescrituras

Hoy reprocesar un link arma una `Note` nueva y conserva sólo lo que se le pasa
a mano (`collections`, `mentions_extra`, `pipeline.py:580`). Una marca que no
se pase se pierde en silencio. Todo camino que reescribe una nota conserva
`mark`, y cada uno tiene un test que lo prueba:

- reprocesar un link (análisis completo);
- el guardado parcial cuando el análisis falla;
- `describe` de una ficha;
- completar una idea y renombrarla;
- renombrar o fusionar una categoría;
- mover de categoría, cambiar etiquetas, `mine` (estado, puntaje, nota).

### Validación

`clean_mark(value) -> str | None` en `vault.py`:

- se recortan los espacios de los bordes; vacío significa "sacar la marca";
- se acepta si tiene entre 1 y 8 code points y ninguno es letra, dígito,
  espacio ni control (categorías Unicode `L*`, `N*`, `Z*`, `C*` salvo ZWJ
  U+200D y el selector de variación U+FE0F, que forman 👍🏽, ❤️ y familias);
- cualquier otra cosa devuelve `None` y no se escribe nada. Los keycaps
  (1️⃣) llevan un dígito y quedan afuera: es el precio de una regla simple.

### Lista fija

`[web] marks = ["⭐", "🔥", "❤️", "📌", "✅", "❓", "💡", "⚠️", "🧪", "📚", "🎯", "👀"]`
es el valor por defecto. Se lee en `Config.marks`; cada entrada pasa por
`clean_mark` y las inválidas se descartan. Ajustes reescribe `config.toml` de
cero, así que también escribe `marks`: si no, guardar Ajustes borraría la
lista de quien la cambió.

### Rutas

- `POST /item/{id}/mark` con `mark` (vacío = sacar) y `back` (la URL relativa
  de la página donde estabas, validada como el resto: sólo un path propio que
  empiece con `/`, nunca `//`). Busca la nota en las tres estanterías, escribe
  con `update_note(..., mark=...)` bajo el mismo lock que el resto, y vuelve a
  `back` con `#card-{id}` para quedar en la misma tarjeta. Una marca inválida
  vuelve con el aviso `bad-mark` y no toca el archivo. Nota inexistente: 404.
  Mismas reglas same-origin que los demás POST.
- `GET /marked?mark=⭐&page=N`: una grilla mixta con las notas de las tres
  estanterías que llevan esa marca, más nuevas primero, paginada como la
  librería. Una marca que nadie usa muestra la página vacía, no un error.

### Interfaz

- `templates/mark-picker.html`, un partial común: un `<details class="mark">`
  cuyo `<summary>` muestra la marca o un ＋ apagado (con `aria-label`
  "Marcar"). Abierto, un form por emoji de la lista (un botón de 44px cada
  uno), un campo "otro" con su botón, y "Quitar" si hay marca.
- Las tres tarjetas (`library.html`, `ocio.html`, `ideas.html`) lo incluyen en
  la esquina superior derecha, fuera del `<a class="body">`, y cada `<li>`
  lleva `id="card-{id}"`. `popup.js` no abre el popup por un clic dentro de
  `.mark`.
- `item.html` lo incluye al lado del título.
- `/marked` dibuja su propia tarjeta, con lo que las tres tienen en común
  (título, categoría, fecha, resumen, marca, portada si hay) y el enlace a la
  página de la nota; no copia las acciones propias de cada estantería.

### Nav

A la derecha de Ajustes, los emojis en uso en las tres estanterías, de más a
menos usado (empate: el orden de la lista fija, después el de aparición),
cada uno un link a `/marked?mark=…` con la cantidad en el `title`. El activo
lleva `class="on"`. Sin marcas, no se dibuja nada. Las cuentas salen de las
estanterías que la app ya mantiene en memoria y se calculan en el contexto
común de las plantillas.

## 2. El celular

Todo esto vale por debajo de 42rem; el escritorio queda como está salvo
donde se dice.

### Cabecera

- Fila 1: la marca, la búsqueda y un `<details class="paste">` con resumen ＋
  que despliega el campo de link y sus dos botones. En el escritorio el
  `<details>` está abierto y el resumen oculto, así que se ve igual que hoy.
- Fila 2: el nav en una línea con scroll horizontal, los emojis al final.
- El botón "Todo" de la cabecera pasa a llamarse "Completo" (en las dos
  pantallas): "Todo" queda sólo para "todas las categorías".
- `autofocus` en la búsqueda sólo en el escritorio: un script de una línea lo
  saca cuando el ancho es de celular.

### Filtros de la librería, ocio e ideas

- Colecciones, categorías, etiquetas y "más etiquetas" van dentro de un
  `<details class="filters" open>`. El resumen dice qué está activo
  ("Filtros · Salud", "Filtros · Todo").
- `static/layout.js` (chico, sin dependencias): si `matchMedia("(max-width:
  42rem)")` coincide al cargar, quita `open` de `details.filters` y de
  `details.paste`, y saca el `autofocus`. Sin JS todo queda abierto, que es lo
  de hoy.
- "Seleccionar" pasa al resumen de los filtros, a la derecha.
- En Ocio e Ideas, los chips de estado entran en el mismo `<details>`; el form
  de idea nueva arranca cerrado en el celular cuando ya hay ideas.

### Línea de tiempo

En el celular deja de ser una fila con scroll: los años en una fila que
envuelve, y los meses del año elegido en una fila propia debajo, también
envolviendo. Para eso la plantilla dibuja los meses en un contenedor aparte
(`<div class="months">`) después de los años, no intercalados. Los nombres
siguen saliendo de `MONTHS` traducidos ("ene", "feb"...). En el escritorio el
contenedor sigue en la columna lateral, debajo de su año como hoy.

### Tarjetas

En el celular la altura es automática y el resumen se corta a 4 líneas
(`-webkit-line-clamp`). En el escritorio sigue la altura fija.

### Objetivos táctiles

En el celular, chips, links del nav, estrellas, el resumen del selector de
marca y los botones de la lista miden al menos 44px de alto (padding, no
fuente más grande).

## 3. Categorías y el resto de las páginas

### Categorías

Una grilla `repeat(auto-fill, minmax(11rem, 1fr))` de tarjetas chicas: el
nombre (link a la librería filtrada), la cantidad grande, y un ✎ que abre un
`<details>` con el campo de renombrar/fusionar y Guardar dentro de la misma
tarjeta. Se mantiene el datalist y la frase sobre fusionar. Ya no hay `ul.hits`
ni filas.

### Acciones ocultas por hover

`@media (hover: none) { .actions { opacity: 1 } }`. En el escritorio siguen
apareciendo al pasar el mouse.

### Resto

- Ítem, ficha, idea: estrellas de 44px; "Abrir el original" y las acciones en
  una fila que envuelve; el selector de marca al lado del título.
- Ajustes: cada motor en una fila compacta (tilde, modelo, "Buscar modelos");
  los proveedores con objetivo táctil de 44px.
- Importar, Reprocesando, Candidatos: capturas a 390px; se corrige scroll
  horizontal o textos cortados si aparecen. Sin rediseño.
- Aviso de notas ilegibles: sólo la cantidad; la ruta en el `title`.
- `:focus-visible` con un contorno claro (token de color, con su versión
  oscura) en links, chips, `summary` y botones.

### Reglas del CSS

Colores sólo como tokens en `:root` con su versión oscura; nada de estilos en
línea; textos nuevos con su traducción en `i18n.py`.

## Pruebas

- Marcas, con TDD: `clean_mark` (aceptados y rechazados, con 👍🏽, ❤️, una
  familia con ZWJ, una letra, "ab", 9 code points, un espacio); `render`/
  `read_note` ida y vuelta; cada reescritura de la lista conserva la marca;
  `POST /item/{id}/mark` en link, ficha e idea, vacío borra, inválido avisa y
  no escribe, `back` ajeno se ignora, 404, same-origin; `/marked` mezcla las
  tres estanterías y pagina; el nav ordena y marca el activo; `Config.marks`
  lee, descarta inválidas y Ajustes la escribe.
- Plantillas: tests de HTML (el `<details class="filters">`, los meses en
  `div.months`, Categorías sin `ul.hits`, "Completo" en la cabecera, `id` de
  tarjeta, `layout.js` cargado).
- Visual: capturas de chromium a 390px y 1366px, claro y oscuro, antes y
  después, de cada página.
- `~/.local/share/oknowledge/venv/bin/python -m pytest -q` completa en verde.

## Fuera de alcance

Más de un emoji por tarjeta; un picker completo; reordenar motores desde la
interfaz; portar esto al fork de Windows (se hace después, aparte).
