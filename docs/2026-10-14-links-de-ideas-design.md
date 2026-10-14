# Links de una idea: a mano y al servicio de la idea

**Fecha:** 2026-10-14 · **Rama:** `feat/idea-links`

Una idea ya puede tener links vinculados (`related` en su nota): se suman desde
la página de un link ("Agregar a una idea") o desde las sugerencias de "Links
que pueden servir a mi idea", y se listan en "Links de esta idea". Lo que falta:

> "El objetivo es tener mas a mano los links que sirvan a esa idea y poder
> realizar acciones en la idea usando esos links, es decir cuando se pide
> ampliar o mejorar la idea puede usar o no esos links para nutrir la idea."
>
> "si hay varios links poder seleccionar uno o mas independientemente para
> usarlos [...] título, resumen y puntos alcanzan. Los links dentro de la idea
> deben ser con formato tarjeta tal cual se muestra en la seccion links.
> Tambien quiero dentro de la idea un buscador de links que al escribir se
> filtra en tiempo real"
>
> "el buscador esta en una seccion a la derecha y debajo del buscador aparecen
> las tarjetas de los links [...] que las tarjetas vinculadas esten arriba del
> buscador en la nueva seccion de la derecha"

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Cómo se elige si Mejorar/Ampliar usan los links? | una casilla general "Usar los links vinculados", marcada, más una casilla por tarjeta, marcadas |
| ¿Se recuerda la selección? | no: cada vez que se abre la idea están todas marcadas |
| ¿Qué de cada link va al modelo? | título, categoría, resumen y puntos clave; nunca la página |
| ¿Qué acciones los usan? | Mejorar y Ampliar. ¿Ya existe? y Links que pueden servir no cambian |
| ¿Cómo se ven los vinculados? | como las tarjetas de la sección Links |
| ¿Dónde? | una columna a la derecha: vinculados arriba, buscador, resultados debajo |
| ¿Cómo busca? | en vivo mientras escribís, con la búsqueda que ya usa la biblioteca |

## 1. La página de la idea en dos columnas

> **Cambio del 2026-10-14, después de usarla:** "tengo que hacer mucho scroll y
> no se ven divididas las secciones [...] el buscador a la derecha y las
> tarjetas que van apareciendo de forma vertical [...] justo debajo del
> buscador". El aside pasa a ser un **panel** con fondo y borde propios, fijo
> en pantalla (`position: sticky`, alto de la ventana), con dos **pestañas**:
> *Buscar* (abierta al entrar: el campo y debajo los resultados) y
> *Vinculados (N/16)* (las tarjetas con Usar y ×). La lista de cada pestaña
> scrollea dentro del panel. Las pestañas son radios y CSS: andan sin
> JavaScript, y las casillas de la pestaña oculta igual viajan con el
> formulario. En el celular el panel va después de los botones, con la lista
> limitada al 70 % del alto. Lo que sigue describe la primera versión.

En pantallas anchas (más de 60rem) la página de una idea usa todo el ancho
(`body.wide`) y una grilla de dos columnas:

- **Izquierda**, como hoy: título, tu texto, la fila de acciones, Guardar, lo
  que escribieron las acciones y la línea de estado/estrellas/pedir de nuevo.
  Su ancho sigue siendo el de lectura (`--measure`).
- **Derecha**, un `<aside class="idea-links">` de unos 24rem, en este orden:
  1. **Links de esta idea** (N/16): las tarjetas vinculadas, una debajo de otra.
  2. **Buscar en tus links**: un campo de texto.
  3. Los resultados de la búsqueda, como tarjetas.

En el celular (y debajo de 60rem) es una sola columna en este orden: la idea
con su fila de acciones y Guardar, después el aside, después lo que
escribieron las acciones y la línea de estado. Así los links quedan cerca de
los botones que los usan. Se arma con `grid-template-areas`, sin duplicar
markup.

La sección "Links de esta idea" de la columna izquierda desaparece: es la del
aside. Si la idea no tiene links, el aside muestra igual el título con
"Ninguno todavía" y el buscador.

## 2. Las tarjetas

Un parcial nuevo, `link-card.html`, con el mismo markup y las mismas clases que
la tarjeta de la biblioteca (`li.card`, `.shot`, `.pad`, `h2`, `a.body`,
`.meta`, `.sum`, `.tags`, `.site`): portada, título que abre el original,
categoría y fecha, resumen, etiquetas, sitio con su ícono. El cuerpo y la
portada abren el popup (`data-popup`), por eso la página de la idea carga
`popup.js`. No lleva el selector de marcas ni el botón de reprocesar: eso
pertenece a la biblioteca, y `library.html` no se toca.

Cada tarjeta recibe sus controles en una franja propia:

- **Vinculada:** una casilla "Usar" y la × para quitarla de la idea (la ruta
  de hoy, `/item/{idea}/related/drop`).
- **Resultado de búsqueda:** el botón "Agregar a la idea" (la ruta de hoy,
  `/item/{link}/ideas` con `back=idea`).

Un link vinculado que ya no está en la biblioteca se ve como una tarjeta
atenuada con su nombre de archivo y la ×, como hoy.

En el aside las tarjetas van en una sola columna; el resumen se corta a tres
líneas para que entren varias sin scroll.

## 3. Usar los links al Mejorar o Ampliar

**El formulario.** Mejorar y Ampliar pasan a postear un mismo formulario
vacío, `act-think`; cada botón lleva su destino en `formaction`
(`/item/{idea}/actions/improve` o `.../expand`). Hace falta porque una casilla
pertenece a un solo formulario, y la misma selección vale para los dos
botones. Las casillas se atan a él con `form="act-think"`:

- general: `name="with_links" value="1"`, junto a los botones, marcada. Sólo
  aparece si la idea tiene al menos un link vinculado que está en la biblioteca.
- por tarjeta: `name="use" value="{stem}"`, marcadas.

Sin JavaScript todo funciona: el servidor sólo mira `use` si llegó
`with_links`. Con JavaScript, destildar la general atenúa y deshabilita las
casillas de las tarjetas, para que se vea que no cuentan.

**El servidor.** `POST /item/{idea}/actions/{action}` acepta `with_links` y
`use` (una lista). Para `improve` y `expand`, si llegó `with_links`, los
stems elegidos viajan a `run_idea_action(..., use=[...])` y de ahí a
`compose`. Para las otras dos acciones se ignoran.

En `compose`, con la idea ya leída:

1. Se quedan sólo los stems que están en `note.related` de la idea, sin
   repetir y en el orden de la idea. Un stem que no está vinculado no se usa
   aunque llegue en el formulario.
2. Cada uno se busca en `cfg.links`; uno que ya no está se saltea.
3. Si no queda ninguno, la acción corre como hoy.

**El prompt.** `idea-improve.txt` e `idea-expand.txt` ganan un marcador
`{{LINKS}}` después de la idea. Vacío cuando no hay links; si hay, un bloque
armado por la app:

```
Links que guardé y elegí para esta idea. Usalos si aportan algo; si no,
ignoralos. No inventes lo que no dicen.

### <título>
Categoría: <categoría>
Resumen: <resumen, hasta 600 caracteres>
Puntos:
- <punto, hasta 200 caracteres>   (hasta 6)
```

El texto de cada link pasa por el mismo saneamiento de una línea que ya se
usa (`_line`), para que un resumen no meta un `{{MARCADOR}}` ni markdown de más.
La sustitución sigue siendo de una sola pasada.

**El resultado.** Cuando se usaron links, la sección que se guarda empieza con
una línea en itálica: *Con 2 links: Título A · Título B.* (en inglés *With 2
links: …*). Así se sabe, en la web y en Obsidian, qué leyó el modelo. Sin
links, la sección es como hoy.

## 4. El buscador

Un campo `<input type="search" name="q">` dentro de un `<form method="get"
action="/item/{idea}">`.

**Endpoint nuevo.** `GET /item/{idea}/buscar-links?q=…` devuelve un fragmento
HTML (`idea-link-results.html`) con hasta 12 tarjetas de la biblioteca
(`cfg.links`), sin las que ya están vinculadas. Usa `Library.search` de la
biblioteca: sin distinguir mayúsculas ni acentos, todas las palabras tienen que
aparecer, título y etiquetas primero. Con menos de 2 caracteres devuelve vacío.
Si no hay resultados dice "Nada coincide". 404 si la idea no existe.

**En vivo.** `idea-links.js`: con cada tecla espera 250 ms sin escribir, pide
el fragmento y lo pone debajo del campo. Si llega la respuesta de una búsqueda
vieja después de una nueva, se descarta. Enter no recarga la página.

**Sin JavaScript.** El formulario hace GET a la página de la idea con `?q=`, y
la página renderiza el mismo parcial en el mismo lugar.

**Agregar.** El botón de cada resultado postea a la ruta de hoy con
`back=idea` y además `q`; la redirección vuelve a la idea con `?q=` para que
los resultados sigan ahí y se puedan sumar varios seguidos. El tope de 16
links y su aviso no cambian.

## 5. Textos (es)

| clave (en) | es |
|---|---|
| Links for this idea | Links de esta idea |
| None yet | Ninguno todavía |
| Search your links | Buscar en tus links |
| Use the linked links | Usar los links vinculados |
| Use | Usar |
| Nothing matches | Nada coincide |
| Add to the idea | Agregar a la idea (la clave ya existe) |

## 6. Pruebas

- `compose` con `use`: el prompt de Mejorar y de Ampliar trae el bloque con
  título, resumen y puntos de los elegidos y no el de los no elegidos.
- Un stem que no está en `related` no entra al prompt.
- Un stem vinculado que ya no está en la biblioteca se saltea; si no queda
  ninguno, el prompt no tiene bloque.
- La sección guardada empieza con "Con N links: …" cuando se usaron, y no
  cuando no.
- La ruta: sin `with_links` no se pasan stems; con `with_links` sí; en
  `exists` y `links` se ignoran.
- Un resumen con `{{TEXT}}` adentro no se sustituye.
- La página de la idea: tarjetas en el aside, casillas marcadas, la general
  sólo con links, Mejorar y Ampliar con `formaction` sobre `act-think`,
  `popup.js` cargado.
- `buscar-links`: filtra, excluye los vinculados, corta en 12, menos de 2
  caracteres da vacío, idea inexistente da 404.
- La página con `?q=` muestra los resultados sin JavaScript.
- Agregar con `q` vuelve a `/item/{idea}?q=…`.
- Capturas en 390px y 1400px de ancho sobre el vault de prueba.

## Fuera de alcance

- Guardar qué links se eligieron.
- Leer la página completa de cada link.
- Usar los links en ¿Ya existe? o en Links que pueden servir.
- Reordenar los links de la idea.

Después del merge en `main`, el cambio se lleva a la rama `windows` del fork
como los anteriores.
