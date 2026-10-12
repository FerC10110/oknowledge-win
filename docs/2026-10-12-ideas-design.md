# Ideas: guardar lo que se te ocurre

**Fecha:** 2026-10-12 · **Rama:** `feat/ideas`

La app guarda links y, desde ayer, fichas de ocio. El objetivo de fondo es un
segundo cerebro, y este es el segundo de tres pasos: una sección donde
escribir las ideas que se te ocurren —una app, un negocio, algo para la casa—
y que no se pierdan en una nota del teléfono.

> "sección de ideas: guardar ideas de apps con acciones de IA"
>
> "al escribir la idea la ia debe completar título, tags y todo lo
> completable, así luego el usuario modifica"

Lo que se quiere acá: escribís el texto, se guarda en el acto, y el modelo le
pone título, etiquetas, un resumen y los puntos mientras vos seguís con lo
tuyo. Después lo corregís todo a mano si querés.

Las acciones de IA sobre una idea —si ya existe en internet, qué se le
parece, cómo mejorarla, cómo ampliarla— son el tercer spec y se construyen
sobre esto.

## Hechos medidos

Todo lo de abajo se leyó del código el 2026-10-12 y manda sobre el diseño.

| Hecho | Dónde | Qué implica |
|---|---|---|
| Un estante es `Shelf(name, dir, index_dir)`, y el de ocio guarda sus índices adentro de sí mismo | `config.py:33`, `config.py:91` | el estante de ideas se declara en tres líneas |
| El contrato de un motor es `complete(prompt: str) -> str` | `ai/base.py` | el modelo no busca ni abre nada por su cuenta: todo lo que sabe se lo pasa la app en el prompt |
| `STATES = ("pending", "doing", "done")`, con su razón escrita al lado | `vault.py:706` | las fichas siguen con tres; las ideas necesitan un cuarto |
| `STATE_WORDS` ya mapea tipo de nota → palabras de la interfaz | `web/app.py:363` | una idea es otra fila de esa tabla, no un sistema nuevo |
| `slug(text, fallback)` cae al id cuando el texto está vacío | `vault.py:87` | una nota todavía sin título igual tiene un nombre de archivo razonable |
| `_rename_to_title()` reescribe la nota y recién después `os.replace`, y hoy está clavado en `cfg.links_dir` | `pipeline.py:650` | el renombre atómico ya existe; sólo hay que dejarlo trabajar en otro estante |
| `my_note` es un campo del usuario que ningún proceso pisa, con su `update_note(my_note=...)` y su ruta `POST /item/{id}/mine/note` | `model.py:68`, `vault.py:688` | el texto de una idea no necesita un campo nuevo ni una ruta nueva: ya existen |
| Un id es `sha256(url normalizada)[:12]` | `urls.py:99` | una idea usa la misma función sobre un uri propio |
| `collections`: campo del usuario, hasta 16, que ningún reproceso pisa | `docs/2026-10-07-colecciones-design.md` | de ahí salen el tope de links y el molde del formulario |
| `describe()` relee la nota bajo el lock y aplica sólo los campos del modelo | `pipeline.py` | el completado de una idea se cuelga de ese mismo esqueleto, ya probado |

## A. El estante

```python
@property
def ideas(self) -> Shelf:
    return Shelf("ideas", self.root / "ideas", self.root / "ideas")
```

Carpeta `ideas/` adentro de la carpeta administrada, con sus índices adentro
del propio estante, igual que el ocio. Link **Ideas** en la barra, al lado de
Ocio; la sección vive en `/ideas`.

Una idea no aparece en la biblioteca de links ni en Ocio, y un link no
aparece entre las ideas. El reindex de un estante no toca los índices de
otro. La papelera sigue siendo una sola para todo.

## B. La idea es una nota

```markdown
---
url: ""
title: Gimnasio con IA
type: idea
tags: [gimnasio, ia, rutinas]
summary: Una app que arma la rutina leyendo lo que levantaste la semana pasada.
state: pending
score: 4
related:
  - "[[2026-10-02-rutina-de-fuerza-en-casa]]"
  - "[[2026-10-05-como-medir-el-rpe]]"
saved: 2026-10-12
id: 7f3a9c2e
---

## Puntos

- Resuelve tener que acordarse de qué se hizo la semana pasada.
- Para alguien que entrena solo y sin entrenador.
- Lee el registro de series y repeticiones y propone la carga siguiente.

## Mi nota

Una app que me arme la rutina del gimnasio según lo que levanté la semana
pasada, y que me vaya subiendo el peso sola.
```

`type: idea` es lo que distingue una idea de una ficha; hoy ese campo ya
lleva `movie`, `series`, `anime` y `book`.

Tu texto se guarda en **`my_note`**, el campo que ya existe para lo que
escribe el usuario y que ningún proceso pisa —es exactamente lo que es— y por
eso editarlo reusa la ruta `POST /item/{id}/mine/note` en vez de una nueva.
El precio es que en Obsidian la sección se titula *Mi nota*: cambiarle el
nombre tocaría el parser de encabezados que comparten todas las notas, en
todos los idiomas, y no lo vale. En la web la etiqueta dice *Tu idea*.

El `points` del modelo se renderiza como `## Puntos clave`, igual que en
cualquier otra nota. El campo `body` —el contenido que un link trae de su
página— queda vacío en una idea.

### Quién escribe cada campo

| campo | lo escribe | ¿lo pisa *pedir de nuevo*? |
|---|---|---|
| tu texto (`my_note`) | **vos** | **nunca** |
| `title` | vos, o el modelo **sólo si lo dejaste vacío** | nunca |
| `tags` | el modelo | sí |
| `summary` | el modelo | sí |
| `points` | el modelo | sí |
| `state` | **vos** | nunca |
| `score` | **vos** | nunca |
| `links` | **vos**, desde la página de un link | nunca |
| `id`, `saved`, `type` | la app, al crear | nunca |

La regla del título no necesita ninguna bandera nueva: el modelo lo completa
sólo cuando está vacío, así que un *pedir de nuevo* no lo pisa jamás —ya no
está vacío—. Si no te gusta el que puso, lo borrás y pedís de nuevo.

Las etiquetas son del modelo, como en todo el resto de la app, y por eso un
*pedir de nuevo* las rehace. Lo que escribís vos y nada pisa nunca son las
colecciones; eso no cambia.

### Los cuatro estados

| guardado | lo que dice el botón |
|---|---|
| `pending` | semilla |
| `doing` | en marcha |
| `done` | hecha |
| `dropped` | descartada |

El repo tiene tres estados y una razón escrita para no tener un cuarto: *"una
lista de cosas que abandonaste es una lista que nadie abre"*. Para una
película se sostiene; para una idea no, porque acordarte de que ya la
descartaste —y de por qué— es justamente lo que le pedís a un segundo
cerebro. Las fichas siguen con tres y las ideas tienen cuatro: el vocabulario
pasa a depender del estante, y la validación del campo `state` pasa a saber
de cuál.

## C. El flujo

### Crear

La sección tiene un botón **Nueva idea** que abre un formulario con un
textarea (requerido) y un campo de título (opcional). `POST /ideas/guardar`:

1. Si el texto viene vacío, aviso y no se escribe nada.
2. Se calcula el id con la misma función que usa un link,
   `link_id("idea:<instante ISO con microsegundos>")` —sha256 de un uri
   propio, los primeros doce— y se escribe la nota con lo que mandaste.
3. Se reconstruyen los índices del estante.
4. Se encola el completado y se te manda a la página de la idea.

No hay promesa de "no duplica": dos veces la misma idea son dos notas. Una
película la identifica el catálogo; una idea no tiene nada que la
identifique más que el momento en que se te ocurrió.

Mientras el modelo piensa, la nota ya está en disco con tu texto. Si todavía
no tiene título, el archivo se llama `2026-10-12-<id>.md`, porque `slug()`
cae al id, y la grilla la marca como todavía sin completar —no tiene
`engine`—, igual que una ficha sin reescribir.

### El completado

Una tarea en la misma cola que usan las fichas, con el prompt nuevo
`idea.txt` al lado de `ficha.txt`. Recibe tu texto y el título si lo
escribiste; contesta JSON con `title`, `tags`, `summary` y `points`, en el
idioma de `cfg.language`. Misma cadena de motores, mismas trazas, mismos
avisos cuando no contesta.

Al volver, relee la nota **bajo el lock** —pasaron minutos y vos pudiste
haber marcado el estado, puesto estrellas o seguido escribiendo— y aplica
solamente sus cuatro campos más `engine` y `model`. Si la nota ya no está,
no la resucita. Si el título estaba vacío y ahora hay uno, el archivo se
renombra con `_rename_to_title()`, que pasa a recibir el estante en vez de
escribir siempre en `links/`.

### Editar

La página muestra el título y el texto en un formulario con **Guardar**,
que postea a la ruta que ya existe, `POST /item/{id}/mine/note`, con el
título como campo opcional que una ficha nunca manda. Si cambiás el título, la nota se reescribe y
el archivo se renombra con el mismo helper atómico. Renombrar una idea no
rompe ninguna referencia: **nadie apunta a una idea**, la relación con los
links vive solamente adentro de la nota de la idea.

### Pedir de nuevo

Un botón en la página encola el mismo completado, para cuando ampliaste el
texto y querés etiquetas, resumen y puntos frescos. Es la ruta que las
fichas ya usan para reescribirse.

### Sumar un link

En la página de un link, un selector con tus ideas y un botón **sumar**, con
el mismo molde que el formulario de colecciones que ya está ahí.
`POST /item/{id}/ideas` toma el lock **de la idea**, la relee, agrega el
wikilink si no estaba y la escribe. Si la idea fue borrada mientras tanto,
aviso y no se escribe nada.

Se eligió esta puerta y no un buscador adentro de la idea porque la relación
se te ocurre leyendo el link, no mirando la idea.

## D. Los links relacionados

La nota de la idea guarda wikilinks: `"[[2026-10-02-rutina-de-fuerza]]"`. Es
lo que hace que la idea se lea sola en Obsidian —la abrís y sus links están
ahí, navegables— que es la razón por la que la relación vive de este lado y
no en el link.

El campo se llama `related` y no `links`: `links` ya es el nombre del estante
de links en todo el código.

- **Tope:** dieciséis, el mismo número que las colecciones. Reusar un número
  ya pensado antes que inventar uno nuevo.
- **Repetidos:** sumar dos veces el mismo link no duplica nada.
- **Al renderizar**, cada wikilink se resuelve contra la biblioteca para
  mostrar el título de verdad, la categoría y la tarjeta. Así un link que
  cambió de título se sigue viendo bien.
- **Una referencia que no resuelve** —la borraste en Obsidian, o a mano— se
  dibuja apagada, con su nombre guardado y una cruz para sacarla.
- **Cuando un link se renombra**, que es lo que hace `_rename_to_title()`
  cuando el modelo por fin le pone título de verdad, el renombre repasa el
  estante de ideas y repunta lo que apuntaba al nombre viejo. El patrón ya
  existe: `rename_category()` barre el vault y reporta cada nota que no pudo
  escribir, en vez de dejar a medias y callarse.

## E. La página y la sección

La sección `/ideas` es una grilla como la de Ocio: lo último arriba, chips
para filtrar por estado y por etiqueta, y las descartadas escondidas salvo
que las pidas. Cada tarjeta muestra el título, el resumen y las estrellas.

La página de una idea muestra, en este orden: el título y el texto en el
formulario editable, los puntos, los links relacionados, los botones de
estado, las cinco estrellas, las etiquetas, *pedir de nuevo* y borrar. Los
controles de estado y estrellas ya existen; una idea los usa tal cual, con
otras palabras.

## Cuando algo falla

| Qué pasa | Qué se ve |
|---|---|
| Guardás sin texto | aviso, no se escribe nada |
| El modelo no contesta, o no contesta JSON | la idea queda guardada con tu texto, sin completar, y se marca como tal |
| Borraste la idea mientras el modelo pensaba | no se resucita; queda borrada |
| Fallan los índices al guardar | la nota igual queda escrita, con el aviso `indexes-stale` |
| El archivo no se puede renombrar | la nota queda con su nombre viejo y se dice por qué, nunca a medio escribir |
| Sumás un link a una idea que ya no está | aviso, no se escribe nada |
| Un `state` escrito a mano en Obsidian | se muestra tal cual, la sección no se cae |
| `?estado=` con algo que no existe | la sección no se vacía |
| Dos pestañas escribiendo la misma idea | cada escritura relee bajo el lock; gana la última, no se pierde la nota |

## Lo que este diseño no hace

- Las acciones de IA —ya existe, similares, mejorar, ampliar— son el spec
  siguiente.
- El modelo no propone links: los sumás vos.
- No hay buscador adentro de la idea, ni orden por estrellas, ni categoría
  por idea, ni exportar, ni compartir, ni adjuntar imágenes.
- El modelo nunca reescribe tu texto. Lo lee.

## Cómo se verifica

TDD con mutación sobre todo lo nuevo, como el resto del repo.

1. **El estante aislado**, en las dos direcciones: una idea no aparece entre
   los links ni en Ocio, y un link no aparece entre las ideas.
2. **Crear**: sin texto no se escribe nada; con texto queda la nota, se
   encola el completado y la página responde.
3. **El completado**: pone título sólo si estaba vacío; no pisa tu texto,
   el estado, las estrellas ni los links; una idea borrada mientras pensaba
   no vuelve; el archivo se renombra cuando llega el título; una respuesta
   que no es JSON deja la idea guardada igual.
4. **Editar**: guardar el texto no pisa nada del modelo salvo lo que
   corregiste; cambiar el título renombra el archivo.
5. **Links**: sumar escribe en la idea; sumar dos veces no duplica; sumar a
   una idea borrada no escribe; quitar saca la fila; una referencia que no
   resuelve se dibuja apagada; el renombre de un link repunta las ideas.
6. **La sección**: filtra por estado y por etiqueta, esconde las
   descartadas, y un `?estado=` inventado no la vacía.
7. **Ningún método seguro escribe en el vault**: lo cubre el meta-test que
   recorre los handlers y los helpers que capturan.

## Después de esto

Queda el tercer spec: las acciones sobre una idea —si ya existe en internet,
qué se le parece, cómo mejorarla, cómo ampliarla, y cuáles de tus links le
sirven—. La decisión ya tomada es que **busca el motor**, no la app, y eso
tiene dos consecuencias que ese spec arranca teniendo que resolver: el
contrato `complete(prompt) -> str`, que hoy entiende todo el repo, se parte
en dos caminos; y con `ollama` la acción no va a existir, así que la interfaz
tiene que decirlo en vez de fallar.
