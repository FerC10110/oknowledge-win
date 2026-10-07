# Colecciones

**Fecha:** 2026-10-07 · **Rama:** `feat/mentions-search`

## El problema

> "quiero agregar un feature nuevo: poder seleccionar tarjetas y darle una
> categoría propia, por ejemplo estoy trabajando en un proyecto entonces
> agrupo los links que me sirven para ese proyecto"

Hoy una nota tiene **una** categoría, que la pone el modelo, y hasta ocho
etiquetas, que también las pone el modelo. Las dos describen de qué habla el
link. Ninguna de las dos sirve para decir "esto lo estoy usando yo, ahora,
para esto": si un proyecto toca cuatro temas, sus links quedan repartidos en
cuatro categorías, y poner la categoría a mano en las cuatro las saca de su
tema real y encima el próximo reproceso la pisa.

Una colección es otra cosa: es del usuario, una nota puede estar en varias, y
nada de lo que hace el programa la toca.

## Decisión

Un campo nuevo, `collections`, en el frontmatter de la nota. No reusamos
`category` (es una sola y la escribe el modelo) ni `tags` (las escribe el
modelo y se normalizan a minúsculas con guiones, que no es como uno escribe
"Casa nueva").

| | categoría | etiquetas | **colección** |
|---|---|---|---|
| quién la pone | el modelo | el modelo | **el usuario** |
| cuántas por nota | una | hasta 8 | **hasta 16** |
| la pisa un reproceso | sí | sí | **nunca** |
| índice `.md` en el vault | uno por categoría | no | **no** |
| forma del nombre | tal cual se escribe | `minusculas-con-guiones` | **tal cual se escribe** |

## El campo

```python
collections: list[str] = field(default_factory=list)
"""Las colecciones del usuario: sus proyectos, sus listas, lo que sea que
esté juntando. Son suyas y el programa no las escribe nunca por su cuenta,
igual que mentions_extra: un reproceso las lleva de una nota a la otra sin
mirarlas."""
```

En `vault.render()` entra en `FRONTMATTER_ORDER` justo después de `tags`, y
**se omite cuando está vacía**, como `cover` y `author`. Si no, las 1181
notas que hay hoy se reescribirían algún día con un `collections: []` que no
dice nada.

Al leer (`read_note`), una `collections` que no sea una lista hace que la
nota **no** se lea — el mismo trato que tiene hoy `tags`, porque un
frontmatter roto a mano es un error que conviene ver.

### El nombre

`normalize_collections(names)`, en `ai/base.py` al lado de
`normalize_tags()`, pero con otra regla, porque acá el que escribe es el
usuario:

* se limpia como una categoría (`_clean_category`): fuera los caracteres de
  control y los que un nombre de archivo no soporta (`\/:*?"<>|`), los
  espacios se juntan, y se recortan puntos y espacios de las dos puntas;
* máximo 80 caracteres, los mismos que una categoría;
* lo que queda vacío se descarta;
* máximo 16 por nota. No es una regla de producto, es un techo: un
  frontmatter que crece sin fin es una nota que algún día no se puede leer.

La limpieza es la de una categoría y no otra porque así una colección puede
tener su propio índice `.md` el día que haga falta, sin migrar nada.

**La mayúscula la decide la ruta, no el vault.** Si el usuario escribe "casa"
y ya tiene una colección "Casa", la nota tiene que ir a "Casa": dos chips que
son la misma cosa son exactamente el desorden del que esto lo saca. Pero
saber qué colecciones existen es cosa del índice de la web, no de
`vault.py` — que lee una nota por vez y no tiene por qué recorrer el vault
entero para guardar una. Así que la ruta busca el nombre canónico en
`library.collections()` comparando con `index.fold` (sin mayúsculas ni
acentos) y le pasa a `update_note()` el que ya existía; `normalize_collections`
sólo limpia.

## Qué pasa en un reproceso

Nada. Es lo que se eligió. En `pipeline.py` hay dos lugares donde se arma la
nota nueva con lo que se conserva de la vieja (líneas 325 y 481, los mismos
que ya conservan `mentions_extra`), y a los dos se les agrega:

```python
collections=(keep.collections if keep else []),
```

Un link que se reprocesa cambia de título, de resumen, de categoría y de
etiquetas. Sus colecciones son del usuario y siguen donde estaban.

## El índice de la web

`Library._refresh()` ya recorre todas las notas una vez; en ese mismo paso
acumula `collections: dict[str, int]`, igual que `categories`. Se publica con
los demás al final, se limpia en la rama de `OSError` junto con
`_categories`/`_tags`/`_tag_home`, y se expone con `collections()`.

`filter()` suma un parámetro:

```python
def filter(self, category=None, tag=None, collection=None) -> list[Note]:
    ...
    if collection:
        found = [n for n in found if collection in n.collections]
```

Los tres se combinan (es un *and*), así que `/?collection=casa&tag=hyprland`
es una pregunta válida y útil.

En la búsqueda, el nombre de la colección entra en el **primer tier**, con el
título y las etiquetas: es la única palabra de la nota que eligió el usuario,
así que buscar "casa" tiene que traer lo de la casa antes que un resumen que
menciona una casa al pasar.

## La URL

`/?collection=casa`, y se combina con `category`, `tag` y `page` como
cualquiera de los otros. Hay que agregarlo en tres lugares que ya conocen
esta lista de parámetros:

* el `params` de la ruta `home()`, para que el paginador lo arrastre;
* `return_url()`, para que el botón de reprocesar de una tarjeta devuelva al
  usuario a la colección donde estaba y no a la biblioteca entera;
* los campos ocultos del formulario `redo` en `library.html`.

## La interfaz

### La fila de chips

Una fila propia **arriba de la de categorías**, y sólo si hay por lo menos
una colección: un usuario que todavía no usa esto no paga ni un pixel. Las
colecciones son el filtro más intencional de los tres, así que van primero.

Sin tope por ahora: son los proyectos de una persona, van a ser cinco o diez.
Si alguna vez crecen, se les pone el mismo `<details>` que ya tienen las
etiquetas.

### Elegir tarjetas

Un enlace **"Seleccionar"** al lado de los chips lleva a `/?pick=1` (más los
filtros que estuvieran puestos). Con `pick`:

* cada tarjeta muestra un `<input type="checkbox" name="id" value="...">`;
* abajo aparece una barra con un campo de texto, un `<datalist>` con las
  colecciones que ya existen y dos botones: **Agregar** y, si se está viendo
  una colección, **Quitar de esta colección**;
* "Seleccionar" pasa a ser "Cancelar", que es volver a la misma URL sin
  `pick`.

Un modo que se prende con una recarga, y no con JavaScript, porque así anda
sin JavaScript — que es como anda todo lo demás de esta aplicación. Una
mejora opcional después: `body:has(.pick:checked) .bulk { ... }` para que la
barra sólo aparezca cuando hay algo marcado, que es CSS y tampoco necesita
script.

**El formulario no envuelve la grilla.** Las tarjetas ya tienen adentro el
`<form class="redo">` de reprocesar, y un formulario adentro de otro es HTML
inválido y los navegadores lo deshacen de maneras distintas. En vez de eso:

```html
<form id="pick" method="post" action="/collections/add"> ... </form>
...
<input type="checkbox" form="pick" name="id" value="{{ note.id }}">
```

El atributo `form` es de HTML5 y hace justo esto: ata el control a un
formulario que está en otra parte del documento. Los dos botones de la barra
mandan al mismo formulario con `formaction` distinto.

### Sacar una nota de una colección

Dos caminos, los dos necesarios:

* en la página de la nota, los chips de sus colecciones con una ✕ que postea
  a `/item/{id}/collections` la lista entera, igual que hoy funcionan las
  etiquetas;
* en la biblioteca, filtrando por una colección y usando la selección: es la
  manera de sacar veinte de una.

## Las rutas

| ruta | qué hace |
|---|---|
| `POST /collections/add` | `name` + muchos `id`: agrega la colección a cada nota |
| `POST /collections/remove` | lo mismo, al revés |
| `POST /item/{id}/collections` | reemplaza la lista entera de una nota |

Las tres pasan por el `edit()` que ya existe en `app.py`, que toma el lock
del link, distingue "no se escribió nada" de "se escribió y los índices
quedaron viejos", y refresca la biblioteca.

**No se reconstruye ningún índice.** Ningún `.md` del vault nombra una
colección, así que `update_note()` las trata como hoy trata `mentions`: se
escribe la nota y se vuelve, sin el `_finish()`. Agregar treinta notas a una
colección escribe treinta archivos y no reconstruye nada.

Las tres llevan los mismos campos ocultos que el formulario de reprocesar
(`back`, `category`, `tag`, `collection`, `page`) y vuelven con
`see_other(return_url(...))`: el usuario marcó diez tarjetas en la página 3
de una colección y ahí tiene que quedar.

Las rutas en lote recorren los ids de a uno, cada uno bajo su propio lock, y
cuentan. Si alguna falla (una nota borrada desde Obsidian entre que se dibujó
la página y se apretó el botón, un link ocupado reanalizándose) **las demás
se hacen igual** y el aviso dice la verdad: "28 de 30". Que una se haya
movido no es razón para no hacer las otras veintinueve.

El `name` que llega vacío o que la limpieza deja vacío se rechaza antes de
tomar ningún lock, con su propio aviso.

## En Obsidian

No se escribe un índice por colección. `collections` es una propiedad del
frontmatter, así que Obsidian ya la muestra en el panel de propiedades, la
busca con `["collections"]` y la lista con Dataview sin que nosotros
escribamos un solo archivo. Un índice por colección duplicaría las reglas de
colisión de nombres que ya tienen las categorías para resolver algo que
Obsidian resuelve solo.

## La CLI

No lleva comando. Seleccionar tarjetas es algo que se hace mirando, y mirando
es en el navegador; a mano se edita el frontmatter en Obsidian. Si algún día
hace falta mover muchas de una, se agrega entonces y con un caso real
adelante.

## Qué se prueba

Con mutación sobre cada cosa nueva, como el resto del proyecto.

**`tests/test_vault.py`**
* una nota con colecciones se escribe y se vuelve a leer igual;
* una nota sin colecciones no escribe la clave en el frontmatter;
* `collections` que no es una lista hace que la nota no se lea;
* `update_note(collections=[...])` reemplaza la lista y **no** reconstruye
  los índices (se verifica mirando el mtime de un índice).

**`tests/test_ai_base.py`** (`normalize_collections`)
* "  Casa   nueva  " queda "Casa nueva";
* "casa" con "Casa" ya existente se guarda como "Casa";
* un nombre de 200 caracteres se recorta a 80;
* `a/b`, `..`, `"x"` pierden lo que no va;
* un nombre que queda vacío se descarta;
* la número 17 no entra.

**`tests/test_pipeline.py`**
* un reproceso cambia título, resumen, categoría y etiquetas, y deja las
  colecciones intactas — en los dos caminos (`analyze` y `retry`).

**`tests/test_web_read.py`**
* `Library.collections()` cuenta bien;
* `filter(collection=...)` filtra, y combinado con categoría y etiqueta
  también;
* la fila de chips no existe si no hay ninguna colección;
* el chip activo se marca y el paginador arrastra `collection`;
* buscar el nombre de una colección la trae primero.

**`tests/test_web_write.py`**
* el POST se arma **parseando el formulario que la página dibuja**, no a
  mano: así, borrar un campo oculto rompe una prueba;
* dos de tres ids existen → se escriben dos y el aviso dice "2 de 3";
* después de agregar, la respuesta devuelve a la misma página y filtro desde
  los que se apretó el botón;
* escribir "casa" teniendo "Casa" guarda "Casa" y no crea un chip nuevo;
* un nombre vacío se rechaza y no escribe nada;
* quitar de una colección deja las otras;
* un id que no existe da 404 y no toca las demás notas.

**`tests/test_i18n.py`** — los textos nuevos en los dos idiomas.

## Lo que no entra

* un índice `.md` por colección en el vault;
* ordenar las notas adentro de una colección, o arrastrarlas;
* colecciones adentro de colecciones;
* una página propia por colección, con su descripción;
* comando de CLI.

Todo eso se puede agregar después sin cambiar nada de lo de arriba. Nada de
eso hace falta para contestar "estoy laburando en esto, ¿qué links tenía?".
