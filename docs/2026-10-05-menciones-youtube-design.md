# Menciones de un video de YouTube — diseño

**Fecha:** 2026-10-05
**Rama:** feat/v1
**Estado:** aprobado en conversación; el usuario revisa este documento y el plan
al despertar. Autorizó explícitamente escribir spec, plan e implementación de
una sola corrida, sin merge, push ni tag.

## Qué se construye

En palabras del usuario:

> Al pegar un link de youtube se debe descargar la transcripcion, hacer resumen
> de que es el video, de que se hablo. Extraer los links o empresas mencionados,
> por ejemplo mencionan opencode o github, quiero tener los links de todo lo
> mencionado en el video con posibilidad de borrar los que no me interesan. El
> objetivo es poder leer el resumen y tener las empresas mencionadas o links para
> yo poder seguir investigando.

La mitad ya existe. `extract/youtube.py` corre el `yt-dlp` del sistema, elige una
pista VTT (subtítulos del autor antes que automáticos, `es`, `es-419`, `en`,
`en-US`), la convierte a texto hablado y la concatena con la descripción en
`Extracted.text`. Ese texto ya le llega al modelo y el resumen ya se escribe.

Lo que falta, y es todo lo que este documento especifica, son **las menciones**:
una lista de lo que el video nombra, cada ítem con un link al que ir, guardada en
la nota, visible al leerla y borrable de a una.

## Decisiones del usuario

Seis preguntas, seis respuestas. Son el marco: el resto del documento las
obedece, no las re-discute.

1. **De dónde sale la URL de algo nombrado solo de palabra** → *solo el nombre,
   link de búsqueda*. El modelo no propone URLs. Nadie inventa.
2. **Qué hacer con una URL que sí aparece de verdad en el video** → *usarla, y
   buscar el resto*. Si la descripción trae el link, la mención queda con ese
   link real; lo nombrado al pasar queda con link de búsqueda.
3. **Alcance** → *solo YouTube*. Para todo otro tipo de link, el prompt y la nota
   quedan exactamente como hoy.
4. **Qué cuenta como mención** → *configurable*, con tres modos para probar y
   quedarse con el que funcione: herramientas y empresas, todo lo nombrable, y
   solo lo que el video discute de verdad.
5. **Borrar y después reprocesar** → *vuelve, el reproceso manda*. Borrar afecta
   la lista actual y nada más. No hay lista de descartados.
6. **Los videos ya guardados** → *un comando para reprocesarlos*, de a tandas y
   repetible. Se construye; no se corre: las llamadas al modelo las decide el
   usuario.

## 1. La nota

### La forma

`model.py` gana:

```python
@dataclass
class Mention:
    """Algo que el video nombra, y un lugar al que ir."""
    name: str
    url: str
```

Las dos siempre llenas. `url` es la real del video o la de búsqueda, nunca vacía:
una mención sin ningún lado al que ir no sirve para lo que el usuario pidió.

`Note` gana `mentions: list[Mention] | None = None`, **tri-estado deliberado**:

| Valor | Significa |
|---|---|
| `None` | nunca se preguntó por las menciones de esta nota |
| `[]` | se preguntó y el video no nombra nada |
| `[...]` | se preguntó y esto es lo que nombra |

La diferencia entre `None` y `[]` no es un lujo: es lo que hace que el comando de
la sección 5 sea idempotente. Sin ella, un video que genuinamente no menciona
nada vuelve a ser candidato cada vez que el comando corre, y cada corrida gasta
una llamada al modelo para volver a no encontrar nada.

### Cómo se escribe

`HEADINGS` pasa de 2-tupla a 3:

```python
HEADINGS = {
    "es": ("Puntos clave", "Menciones", "Contenido original"),
    "en": ("Key points", "Mentions", "Original content"),
}
```

`render()` escribe la sección cuando `mentions is not None`, **después de los
puntos y antes del contenido** — obligatorio en ese orden, porque la sección de
contenido corre hasta fin de archivo por diseño (así los encabezados que vengan
dentro del texto extraído sobreviven):

```markdown
## Menciones

- [opencode](https://opencode.ai)
- [Railway](https://duckduckgo.com/?q=Railway)
```

Un `[` o un `]` en el nombre se escribe escapado (`\[`, `\]`) y se desescapa al
leer. Obsidian lo respeta y el nombre no se mutila.

### Cómo se vuelve a leer

Cuidado con un detalle que muerde: hoy `_CONTENT_HEADINGS` se arma con `h[1]`
de cada `HEADINGS`, que al agregar "Menciones" en el medio pasa a ser otra cosa.
Tiene que moverse a `h[2]`, y `_MENTIONS_HEADINGS` toma `h[1]`. Un cambio de
tupla que parece cosmético y silenciosamente rompe el parseo del contenido.

`_split_body` devuelve una tupla de 4 y reconoce la sección por el texto del
encabezado, igual que las otras dos, con la misma guarda: una vez que empezó el
contenido, ningún encabezado se interpreta más. Las notas viejas no tienen la
sección y leen `None`. No hay migración.

El parseo es deliberadamente indulgente, porque esta sección se edita a mano:

| Línea | Se lee como |
|---|---|
| `- [opencode](https://opencode.ai)` | `Mention("opencode", "https://opencode.ai")` |
| `- Caddy` | `Mention("Caddy", <link de búsqueda>)` |
| cualquier otra cosa | `Mention(<la línea tal cual>, <link de búsqueda>)` |

Nada de lo que el usuario escriba en esa sección se destruye. Es la misma regla
que ya rige en el resto del proyecto: un link no se pierde, y las palabras del
usuario tampoco.

## 2. De dónde salen

Solo cuando `Extracted.type == "youtube"`. Para cualquier otro tipo, el prompt
armado es **byte por byte el de hoy**: ni la clave en el esquema, ni la sección
en la nota. Eso se prueba, no se asume (sección 7).

### El prompt

`ai/base.py` tiene hoy un condicional único y hardcodeado:

```python
r"\{\{IF_KNOWN\}\}\n(.*?)\{\{ELSE\}\}\n(.*?)\{\{END\}\}\n"
```

Corre **antes** de la pasada de valores, y el comentario del código dice por qué:
así nada del contenido de la página puede alcanzarlo. Esa propiedad no se toca.

Se generaliza a condiciones con nombre, `{{IF_<NOMBRE>}} … {{ELSE}} … {{END}}`,
resueltas contra un diccionario de banderas (`KNOWN`, `MENTIONS`). Es el mismo
mecanismo con un nombre más, en el mismo lugar de la secuencia. En `analyze.txt`
quedan dos regiones condicionales: la línea del esquema y el párrafo de
instrucciones.

Los tres modos son fragmentos de texto en `prompts/mentions-tools.txt`,
`mentions-all.txt` y `mentions-discussed.txt`, inyectados como `{{SCOPE}}`
**dentro** del bloque condicional. Van en archivos y no en un diccionario de
Python porque el texto de los prompts de este proyecto vive en `prompts/`, y
tres párrafos no son razón para romper eso.

**Los nombres son planos y los fragmentos no llevan marcadores.** Dos
restricciones que parecen arbitrarias y no lo son:

- `pyproject.toml` declara `package-data = ["prompts/*.txt", ...]`, un glob de un
  solo nivel. Un `prompts/mentions/tools.txt` lo encuentra el install editable y
  no lo lleva el wheel: todos los tests en verde y roto para quien instale
  normal. Un test en `test_packaging.py` vigila el caso, y tiene que usar
  `PurePosixPath.full_match` y no `fnmatch`, porque en `fnmatch` el `*` cruza
  las barras y el guardia pasaría de largo exactamente el caso que vigila.
- La pasada de valores es un solo `re.sub`, que no re-escanea lo que una
  sustitución inserta. Un `{{LANGUAGE}}` dentro de un fragmento saldría literal.
  Los fragmentos son texto plano, y un test comprueba que ninguno contenga
  `{{` para que la restricción esté impuesta y no solamente recordada.

Al modelo se le pide:

```json
"mentions": [{"name": "<lo que el video nombra>",
              "url": "<la URL sólo si aparece en el video; si no, vacío>"}]
```

### Cómo llega el modo hasta el prompt

El modo es config y el tipo es del `Extracted`, así que los dos viajan por la
cadena que ya existe. Las firmas que cambian, todas con default para que ningún
llamador de hoy se rompa:

```python
render_prompt(text, meta, known, language, limit=DEFAULT_LIMIT, mentions=None)
analyze(engine, text, meta, known, language, mentions=None)
analyze_with_chain(cfg, text, meta, known, ..., mentions=None)
```

`mentions` es el modo (`"tools"`, `"all"`, `"discussed"`) o `None`. `None`
significa "no pidas menciones" y es lo que recibe todo lo que no es YouTube.
Quien decide es el pipeline, que es el único que ve el `Extracted.type` y la
`Config` al mismo tiempo: pasa `cfg.mentions` cuando el tipo es `youtube` y
`None` en cualquier otro caso.

### La garantía, en código

Una URL que el modelo devuelve se guarda **solo si ese string aparece
literalmente en el texto que se le mandó** (descripción + transcript). Si no
aparece, se reemplaza por el link de búsqueda.

"El texto que se le mandó" es literal y es importante: `render_prompt` corta el
contenido en `limit` antes de armar el prompt, y la comparación tiene que ser
contra **ese** recorte, no contra el transcript completo. Un video de dos horas
se manda truncado; una URL que vive solo en la cola que se descartó es una URL
que el modelo nunca vio, y aceptarla porque coincide con el transcript completo
sería aceptar una invención que acertó de casualidad. La guarda compara contra lo
que viajó.

Esto es el centro del diseño. La decisión del usuario fue "nadie inventa", y una
instrucción en el prompt es algo que el modelo puede desobedecer sin que nos
enteremos. Una comparación de substring no. La promesa la hace cumplir el código.

Casos que la guarda cubre sola, sin reglas extra: una URL recordada de
entrenamiento, un dominio parecido, un sitio muerto que el modelo asoció, un
`example.com` del propio esquema del prompt.

### El link de búsqueda

`https://duckduckgo.com/?q=` + el nombre percent-encoded. Una constante, no una
opción de config: es un default que se cambia editando una línea, y nadie pidió
elegir buscador.

### Lo demás del parseo de la respuesta

- `Analysis` gana `mentions: list[Mention]`.
- **Nunca obligatoria.** `mentions` no entra en `REQUIRED`. Si el modelo no la
  manda, la manda vacía o la manda mal, el resultado es lista vacía y la nota se
  guarda igual. Hacerla obligatoria haría que `analyze()` reintentara con el
  sufijo estricto y, al segundo fallo, perdiera la nota entera por una lista.
  Eso contradice la regla más fuerte del proyecto.
- Un ítem que es un string pelado en vez de un objeto se acepta como nombre, con
  link de búsqueda. Es la forma en que un modelo chico contesta esta clase de
  pedido más seguido que ninguna otra, y descartarla vaciaría la lista justo con
  los motores locales.
- Ítems malformados (ni objeto ni string, sin `name`, nombre vacío, nombre que es
  un placeholder del esquema) se descartan **de a uno**, no tiran el resto.
  `_is_placeholder` ya existe y se reusa.
- Nombre de más de 80 caracteres: truncado.
- Duplicados por nombre plegado (`_fold`, que ya existe y ya maneja acentos y
  otros alfabetos): gana el que tiene link real.
- Tope de 30 menciones por nota.

## 3. La config: los tres modos

`Config` gana `mentions: str = "tools"`, con valores `tools`, `all` y
`discussed`. En `config.toml` es una línea. Un valor desconocido es
`ConfigError` nombrando los tres válidos, como el resto de la validación de este
archivo, que el usuario escribe a mano.

En la página de ajustes, un `select` con los tres, etiquetas en castellano vía
`i18n`. Default `tools`: es el modo que corresponde a los dos ejemplos que dio el
usuario (opencode, GitHub) y el que produce listas que no hay que podar.

Para comparar modos se reprocesa el mismo video y se miran las dos listas. Eso ya
funciona y no hay nada que construir.

## 4. La web

### Leer

`item.html` y `embed.html` muestran la sección cuando la lista tiene algo, en el
mismo lugar relativo que en el archivo: después de los puntos. Una mención cuyo
link es de búsqueda se marca visiblemente —se reconoce comparando contra la misma
constante con la que se construye, no contra una lista de buscadores— para que se
vea de un golpe cuál link salió del video y cuál es una búsqueda. Es la distinción
que el usuario eligió en la pregunta 2 y tiene que ser legible sin pensar.

### Borrar

Solo en `item.html`. `embed.html` no lleva los botones y la razón está escrita en
el propio template: es un fragmento que no escribe nada, y el comentario de su
cabecera lo declara. Respetarlo es más importante que ahorrar un clic.

- Ruta `POST /item/{link_id}/mentions/delete`, campo `name`, un formulario
  chico por fila. Sigue la forma de las rutas que ya existen
  (`/category`, `/tags`, `/delete`, `/reprocess`).
- `update_note()` gana un parámetro `mentions=`.
- **No se reconstruyen los índices.** `_finish()` corre un `rebuild_indexes`
  completo, y los índices listan categoría y título: ninguna mención aparece en
  ninguno. Con 1227 notas, reconstruir todo en cada clic de borrado es trabajo
  real a cambio de nada.
- Borrar una mención que ya no está (doble clic, pestaña vieja) es un no-op, no
  un 500. Una nota que no es nuestra o no existe es 404, como las otras rutas.

### Reprocesar

El reproceso trae las menciones de nuevo, las borradas incluidas. Es la decisión
5 del usuario y es la que mantiene una sola fuente de verdad: lo que ves es la
respuesta del análisis. El texto de confirmación de `Reprocess` enumera hoy lo
que se reemplaza ("title, summary, points, category and tags") y pasa a nombrar
también las menciones. Como en `i18n` la clave **es** el texto inglés, cambiarlo
es cambiar la clave: hay que mover la entrada castellana con él, o la traducción
queda huérfana y la advertencia sale en inglés. Las cadenas nuevas son
`"Mentions"`, la etiqueta del link de búsqueda y la del botón de borrar, más las
tres etiquetas de los modos en ajustes. Una advertencia que no dice la verdad completa es peor que
ninguna.

## 5. El comando para los videos ya guardados

`oknowledge mentions [--limit N] [--json]`, con la forma de `icons`, que ya es un
comando-sustantivo que rellena algo que falta en toda la biblioteca.

**Recorre las notas con `type == "youtube"` y `mentions is None`**, ordenadas
por `saved` descendente (las más nuevas primero, como `retry`), hasta `--limit`. Repetible e idempotente: una nota ya preguntada deja de
ser candidata, incluso si la respuesta fue vacía (para eso existe el tri-estado).

**Es una pasada de solo-menciones, no un reproceso.** Un prompt propio
(`prompts/mentions-only.txt`) que devuelve únicamente la lista, y la escritura
toca únicamente la sección de menciones: el título, el resumen y los puntos que
el usuario ya leyó no se reescriben. Un comando cuyo trabajo es agregar una lista
no tiene por qué cambiar un resumen.

Ese prompt inyecta el mismo `{{SCOPE}}` que el grande y usa los mismos
tres fragmentos: el modo configurado manda acá también, o el comando contradiría
los ajustes. La función que lo corre es

```python
mentions_only(engine, text, meta, language, mode) -> list[Mention]
```

y comparte con el camino grande el parseo de los ítems y la guarda de substring:
una sola implementación de las reglas de la sección 2, llamada desde los dos
lados. Duplicarlas sería tener dos definiciones de "nadie inventa".

El texto del video sale de donde ya está: si la nota se guardó con
`content == "full"`, el transcript está en `note.body` y no hace falta ni red ni
`yt-dlp`. Si se guardó como `summary`, se vuelve a extraer por el camino normal.
La guarda de la sección 2 se aplica igual, contra ese mismo texto.

Códigos de salida como `retry`: `0` todas listas, `1` quedó alguna sin terminar,
`2` un `--limit` negativo. Con `--json`, un solo documento en stdout.

No corre solo y no se corre en esta implementación.

## 6. Errores y casos límite

| Situación | Qué pasa |
|---|---|
| El video no tiene ni descripción ni subtítulos | `Unreadable`, igual que hoy. Sin cambios. |
| El modelo no manda `mentions` | Lista vacía. La nota se guarda. Sin reintento. |
| El modelo manda `mentions` que no es una lista | Lista vacía. La nota se guarda. |
| Un ítem es un string pelado (`"opencode"`) | Se acepta: ese es el nombre, con link de búsqueda. |
| Un ítem no es ni objeto ni string, o no tiene `name` | Se descarta ese ítem. |
| `name` vacío, o es un placeholder del esquema | Se descarta ese ítem. |
| `url` que no aparece en el texto del video | Link de búsqueda. |
| `url` que aparece pero no es `http`/`https` | Link de búsqueda. |
| Dos menciones con el mismo nombre | Una, la que tiene link real. |
| Más de 30 menciones | Las primeras 30. |
| Una nota que no es de YouTube con sección de menciones a mano | Se lee y se muestra. No se borra nada del usuario. |
| Viñeta a mano que no parsea | Se guarda como nombre con link de búsqueda. |
| Borrar una mención que ya no está | No-op. |
| `yt-dlp` no instalado, en el comando de la sección 5 | Esa nota queda sin terminar y se reporta; las demás siguen. |

## 7. Pruebas

Con TDD, y cada una tiene que poder fallar por una razón concreta:

**La nota, ida y vuelta.** Una nota con menciones se escribe y se vuelve a leer
igual. Una sin la sección lee `None`. Una con la sección vacía lee `[]`. Un
nombre con `[`/`]` sobrevive. Una viñeta sin link, y una viñeta que no parsea, se
leen como nombre. Un `## Menciones` **dentro** del contenido original no se
interpreta como encabezado.

**El prompt.** Un link que no es de YouTube produce un prompt sin la clave
`mentions` y sin el párrafo — comparado contra el prompt de hoy. Cada uno de los
tres modos mete su propio fragmento. El condicional generalizado sigue corriendo
antes de la pasada de valores: un `{{IF_MENTIONS}}` escrito dentro del texto del
video no se interpreta.

**La garantía.** Una respuesta con una URL que no está en el texto queda con link
de búsqueda. Una con una URL que sí está, la conserva. Es el test que define la
función: si se borra la guarda, falla.

**El parseo tolerante.** Cada fila de la tabla de la sección 6 que corresponde al
análisis, con su propio test.

**La config.** Los tres valores se cargan; un cuarto es `ConfigError` que nombra
los válidos; el default es `tools`.

**La web.** La sección aparece cuando hay menciones y no cuando no. El link de
búsqueda se distingue del real. Borrar quita una y deja el resto. Borrar no
reconstruye índices. `embed.html` no trae formularios de borrado. Una nota
inexistente da 404.

**El comando.** Elige solo videos sin preguntar; respeta `--limit`; no reescribe
título, resumen ni puntos; usa `note.body` cuando está y no toca la red; un
`--limit` negativo sale 2; `--json` es un solo documento.

## 8. Lo que queda afuera, a propósito

- **Lista de descartados.** Decisión 5 del usuario: el reproceso manda.
- **Menciones en otros tipos de link.** Decisión 3. El condicional con nombre
  deja el lugar hecho si algún día se quiere.
- **Verificar por HTTP una URL propuesta.** El usuario descartó que el modelo
  proponga URLs, así que no hay nada que verificar por red: la guarda de
  substring alcanza y no cuesta una petición.
- **Convertir una mención en nota de la biblioteca.** Nadie lo pidió. El link se
  abre y con eso se investiga, que es el objetivo que el usuario escribió.
- **Rehacer menciones que ya existen** (para comparar modos sobre toda la
  biblioteca). Se compara reprocesando un video desde la web.
- **Elegir buscador.** Una constante.
