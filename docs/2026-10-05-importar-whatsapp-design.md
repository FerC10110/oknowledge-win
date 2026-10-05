# Importar links desde un export de WhatsApp

## Contexto

El diseño original de oknowledge arranca diciendo: *"Guardo links en
favoritos, en WhatsApp y en archivos de texto, y nunca vuelvo a verlos"*. Esto
resuelve la parte de WhatsApp, hacia atrás: hay un export con **1215 links**
acumulados desde julio de 2019, mezclados entre números de teléfono, notas
sueltas y comandos, porque el chat se usó como anotador general.

El objetivo es que esos 1215 links entren a la biblioteca **con la fecha en
que se mandaron**, no con la de la importación. Esa fecha es lo que después
hace útil recorrer seis años de links.

Lo que no entra acá: la línea de tiempo vertical de la biblioteca. Es el otro
subsistema de la misma idea, es mucho más chico y tiene su propio diseño. Este
documento es la condición previa: sin links fechados no hay nada que recorrer.

## Decisiones

- **Importar es rápido; analizar es aparte.** La importación guarda cada link
  como nota `partial` con su fecha y nada más. Analizar 1215 links son 10 a 20
  horas de fetch y motor, así que no se hace en la importación: se hace
  después, de a tandas, con la cola que ya existe para eso.
- **No se pierde un link.** La regla que manda sobre las demás, igual que en
  el resto del sistema. Un link que el parser capturó y no pudo guardar se
  reporta; no desaparece en silencio.
- **El comentario del mensaje se conserva.** El texto que acompaña al link es
  lo único humano que la nota tiene hasta que se analice. Queda como resumen
  provisorio y, además, en el cuerpo de la nota, así que el análisis posterior
  no lo borra.
- **Los dominios sueltos se capturan.** Están escritos a mano y son muchos.
  La ambigüedad con las extensiones de archivo se resuelve con una regla
  explícita, no se esquiva.
- **`--dry-run` antes de escribir.** Lista lo que capturaría, separando los
  dominios sueltos de los `https://` completos, y además los mensajes que
  parecen tener link y no matchearon. Es la red que convierte las heurísticas
  del parser en algo revisable.
- **Reimportar es seguro.** Deduplica por id contra el vault y contra la cola,
  así que correr el mismo archivo dos veces no duplica nada.
- **El parser no toca disco ni red.** Es una función de texto a lista, para
  que se pueda probar con un string y sin un vault.

## El formato de entrada

El export de **Android**, una línea por mensaje:

```
18/7/2019, 11:36 - Fer: https://scratux.org/#download
23/7/2019, 11:39 - Fer: sudo chkrootkit
21/7/2019, 13:50 - Fer: “Easy DevOps for Data Science” by George Seif https://link.medium.com/JfoglQ1zvY
```

`D/M/AAAA, HH:MM - Remitente: mensaje`. Sin corchetes y sin segundos, a
diferencia del export de iOS. Día y mes sin cero adelante.

### El orden de día y mes

`18/7/2019` y `28/7/2019` prueban que este archivo es día primero, pero el
formato depende del idioma y la región del teléfono, así que se detecta en vez
de asumirse:

1. Se recorren todos los timestamps del archivo.
2. Si algún primer campo pasa de 12 → **día primero**.
3. Si no, y algún segundo campo pasa de 12 → **mes primero**.
4. Si las dos cosas pasan → el archivo es inconsistente: se aborta con un
   error que dice qué dos líneas se contradicen. No se adivina.
5. Si ninguna pasa (un export de menos de 13 días) → **día primero**, y la
   salida lo dice explícitamente, para que el usuario pueda desmentirlo.

El año puede venir con 4 dígitos (`2019`) o con 2 (`25`); con 2 se interpreta
como `2000 + n`.

### Mensajes de varias líneas y del sistema

Una línea que no empieza con el timestamp es **continuación** del mensaje
anterior, así que un link partido en dos líneas no se parte.

Del resto de la línea se separa el remitente con el **primer `: `**. Si no hay
ninguno —los avisos del sistema, tipo `Fer creó el grupo`— el remitente queda
vacío y todo el resto es el mensaje. Los links se buscan igual, porque un link
dentro de un aviso del sistema sigue siendo un link. Limitación conocida y
aceptada: un remitente cuyo nombre contenga `: ` se parte mal; cuesta más
detectarlo que lo que vale.

## El parser

Módulo nuevo `src/oknowledge/whatsapp.py`.

```python
@dataclass
class Imported:
    url: str          # con esquema, lista para normalize()
    sent: str         # YYYY-MM-DD, del timestamp del mensaje
    comment: str      # el mensaje sin los links, o ""
    sender: str       # quien lo mandó, o "" en un aviso del sistema
    raw: str          # el link tal como estaba escrito, para el dry-run
    bare: bool        # True si venía sin esquema

@dataclass
class Scan:
    links: list[Imported]
    suspicious: list[str]   # mensajes con un punto entre letras y sin link
    messages: int           # cuántos mensajes se leyeron
    day_first: bool         # qué orden de fecha se detectó
    assumed: bool           # True si el orden se asumió por falta de evidencia

def parse(text: str) -> Scan: ...


class BadExport(Exception):
    """El archivo no es un export que se pueda leer."""
```

`parse()` levanta `BadExport` en los dos casos en que seguir sería adivinar:
ninguna línea con el formato, y un orden de fecha inconsistente. Todo lo demás
—mensajes raros, líneas sueltas, avisos del sistema— no es un error: es ruido,
y el parser lo saltea. El CLI traduce `BadExport` a código 2.

### Qué cuenta como link

**Primero los completos:** `https?://` seguido de lo que no sea espacio.

**Después los sueltos**, en lo que quedó. Un dominio suelto cuenta si su TLD
está en `TLDS` **y** además: o tiene path, o su TLD no está en `EXTENSIONS`.

| Escrito | Decisión | Por qué |
|---|---|---|
| `youtu.be/abc` | captura | `.be` conocido, tiene path |
| `scratux.org` | captura | `.org` conocido, no es extensión |
| `www.foo.com` | captura | idem |
| `example.py/docs` | captura | tiene path, es un dominio de verdad |
| `script.py` | descarta | TLD que también es extensión, sin path |
| `README.md` | descarta | idem |
| `config.json` | descarta | `.json` no es TLD |
| `3.10` | descarta | no son letras |
| `fer@gmail.com` | descarta | precedido por `@`: es un mail |

Las dos listas son constantes de este módulo, para afinarlas después del
`--dry-run` sin tocar lógica:

```python
TLDS = frozenset("""
com org net io dev app me tv co info biz xyz online site tech blog news edu
gov mil ar es mx cl uy pe br us uk de fr it nl pt ru jp cn in au ca ch se no
fi dk pl cz gr tr il za kr be at ie nz eu gg to ly am st fm cc tk link page
cloud space live work wiki art design studio club shop store
""".split())

# TLDs reales que también son extensiones de archivo que este usuario escribe.
# Sin path, gana la extensión. `zip` y `mov` están acá porque Google los
# vendió como TLD y la colisión es peor que las otras.
EXTENSIONS = frozenset("sh py md ts js rs go pl so rb cs ai zip mov".split())
```

### Puntuación y esquema

- Se recorta la puntuación pegada al final: `.,;:!?)]}` y comillas, rectas y
  tipográficas. Aplica igual a los `https://` completos, porque
  `(https://e.com/x)` y `mirá github.com/y.` son los dos casos reales.
- A un dominio suelto se le antepone `https://`. Si el sitio sólo habla http,
  el fetch falla al analizar y la nota queda `partial` con su link intacto.
- El comentario es el mensaje con todos los links capturados sacados, espacios
  colapsados y recortado. Si queda vacío, es `""`.

## La escritura en bloque

Función nueva `pipeline.import_links()`.

```python
@dataclass
class ImportResult:
    found: int                       # links capturados del archivo
    saved: int                       # notas nuevas escritas
    already: int                     # ya estaban en el vault o en la cola
    failed: list[tuple[str, str]]    # (url, por qué) — ninguno se pierde callado
    duplicated: int                  # el mismo link repetido en el chat

def import_links(cfg: Config, items: list[Imported],
                 queue: Queue | None = None) -> ImportResult: ...
```

### Por qué no llama a `add()` por link

Medido en este repo, con un vault sintético:

| notas en el vault | `find_note` | `rebuild_indexes` | por link |
|---|---|---|---|
| 100 | 80 ms | 80 ms | 160 ms |
| 300 | 221 ms | 236 ms | 457 ms |
| 600 | 467 ms | 470 ms | 937 ms |
| 1200 | 916 ms | 943 ms | 1859 ms |

`_scan()` no cachea: glob y parsea cada `.md` del vault, cada vez. Cada
`add()` lo hace dos veces —`find_note` para deduplicar y `rebuild_indexes` al
guardar— y además reescribe todos los índices. Para 1215 links eso es
cuadrático: **~19 minutos de puro trámite**, antes de tocar la red, y 1215
tandas de reescritura de índices dentro de un vault de Obsidian que sincroniza
y reindexa en cada una.

La importación hace los pasos caros **una vez para el lote**:

1. Un escaneo del vault → el conjunto de ids que ya están.
2. Deduplicar dentro del lote. Si el mismo link aparece varias veces en el
   chat, gana **la fecha más vieja**: es cuándo lo guardó por primera vez.
3. Por cada link nuevo, y **tomando su candado** (`q.lock(link_id)`):
   - Chequear `q.get(link_id)`, y contarlo como tomado **sólo si su
     `updated` es igual o posterior al arranque de la importación**. Eso
     cierra la ventana entre el escaneo inicial y ahora —`add()` siempre
     encola— al precio de leer un JSON en vez de escanear el vault. La
     condición de tiempo importa: una entrada vieja de una nota que el
     usuario después borró de la web no tiene que impedir que el link
     vuelva a entrar, porque el vault es la fuente de verdad y la cola es
     sólo bookkeeping.
   - Escribir la nota parcial con `write_note()`.
   - `q.enqueue()` y `set_status(partial)`, así `retry` la puede terminar.
4. **Un** `rebuild_indexes()` al final.

Lo que se abarata son los escaneos y los índices, no las garantías. Se siguen
cumpliendo: sólo escribe dentro de `oknowledge/`, todo pasa por
`write_note()` y por lo tanto por `ensure_inside_root` y el marcador
`oknowledge: 1`, deduplica por id, toma el candado por link, y cada link deja
entrada en la cola.

### La nota que se escribe

El `_partial_note()` que ya existe, con tres diferencias:

| campo | valor |
|---|---|
| `saved` | la fecha del mensaje, **no** la de hoy |
| `summary` | el comentario del mensaje; si no hay, el `PARTIAL_SUMMARY` de siempre |
| `body` | el comentario del mensaje, o `None` |
| `status` | `partial` |
| `content` | `cfg.default_content`, igual que `add()` |
| `category` | `Sin clasificar`, igual que cualquier nota parcial |

El comentario va a los dos lugares a propósito: en `summary` para que la
tarjeta diga algo ahora, y en `body` para que esté completo en la nota y no
recortado por la tarjeta.

**Hasta que se analice, y no más.** `_process()` arma la nota analizada con
`body=page.text`, así que el análisis reescribe los dos campos y el comentario
de WhatsApp se pierde: lo reemplazan el resumen del modelo y el texto de la
página. Eso es lo que "provisorio" quiere decir acá, y es a propósito —
conservarlo para siempre pediría una clave nueva en el frontmatter, que es
justo lo que este proyecto evita (la misma razón por la que los favicons se
guardan por dominio y no en la nota). Si después resulta que vale conservar
las palabras del usuario, es un cambio chico y aparte.

## El arreglo de la fecha

`saved=_today()` está clavado en dos lugares de `pipeline.py`: la nota parcial
(línea 275) y la nota analizada (línea 411). Como el camino elegido es
importar → `partial` → `retry`, el segundo paso **le pisa la fecha de WhatsApp
con la de hoy**. Sin este arreglo se importan 1215 notas fechadas entre 2019 y
2025 y al analizarlas se apilan todas en el mismo día.

Los dos pasan a `saved=(existing.saved if existing else _today())`.

No es un caso especial de la importación: una nota se guardó cuando se guardó,
y reanalizarla no la vuelve a guardar. Es un bug que la importación expone, y
se arregla donde está.

## La interfaz

| Comando | Qué hace |
|---|---|
| `oknowledge import ARCHIVO` | importa; termina en segundos |
| `oknowledge import ARCHIVO --dry-run` | lista qué capturaría, no escribe nada |
| `oknowledge import ARCHIVO --json` | el `ImportResult` como un objeto, para el plugin |
| `oknowledge retry --limit N` | analiza N y para |

Salida de `import`, en una línea por dato y en inglés como el resto del CLI:

```
1215 links in 4120 messages (dates read as day/month)
1198 saved, 17 already there, 9 repeated in the chat
12 of them were written without a scheme
3 messages look like they had a link and did not match (see --dry-run)
```

La línea del formato de fecha está siempre, no sólo cuando se asumió: es el
dato con el que el usuario puede desmentir al parser de un vistazo. Cuando se
asumió por falta de evidencia, agrega `(assumed)`.

El CLI imprime datos de los dos lados: `messages`, `suspicious` y el orden de
fecha salen del `Scan` del parser; `saved`, `already`, `duplicated` y `failed`
del `ImportResult` de la escritura. El comando los tiene a los dos.

`--dry-run` agrega las tres listas que hacen revisable al parser: los
`https://` completos, los dominios sueltos —que es donde puede haber falsos
positivos— y los mensajes sospechosos, que es donde puede haber links
perdidos.

### `retry --limit N`

Corta después de N links **terminados**, no intentados: un link que la cola
tenía y resultó estar ya saldado no consume cupo, porque eso no es trabajo.

El orden es **de lo más nuevo a lo más viejo**, que son los links con más
chance de estar vivos y de importar. La fecha no está en la cola —`updated`
de un lote importado es el mismo para todos— así que sale del `saved` de la
nota: un escaneo del vault por corrida de `retry`, ~1 s con 1215 notas, no uno
por link.

Sin `--limit` se comporta como siempre, así que nada de lo que ya existe
cambia de significado.

## Errores

| Qué pasa | Qué hace | Código de salida |
|---|---|---|
| el archivo no existe o no se puede leer | lo dice y no escribe nada | 2 |
| el archivo no tiene ninguna línea con el formato | lo dice, nombra el formato que esperaba y muestra la primera línea del archivo | 2 |
| el orden de fecha es inconsistente | lo dice y nombra las dos líneas que se contradicen | 2 |
| una nota no se puede escribir | sigue con las demás y la reporta en `failed` | 1 |
| ninguna nota se pudo escribir | lo dice | 1 |
| todo bien, con links ya guardados | normal, los cuenta en `already` | 0 |

Un error al escribir una nota no aborta la importación: 1214 links guardados y
uno reportado es mejor que 1215 sin guardar. El código 1 significa lo mismo
que en el resto del sistema: corrió, pero algún link quedó sin terminar.

## Pruebas

**El parser**, con strings, sin vault ni red:

- la línea de ejemplo real, de punta a punta
- las dos variantes de año, 4 dígitos y 2
- un mensaje de varias líneas con el link partido
- un aviso del sistema sin remitente, con y sin link
- cada fila de la tabla de "qué cuenta como link", como test parametrizado
- un mail, que no se captura
- puntuación pegada: `(https://e.com/x)`, `github.com/y.`, `“e.com/z”`
- orden de fecha: día primero detectado, mes primero detectado, inconsistente
  que aborta, y ambiguo que asume y lo dice
- un archivo vacío, y uno sin ninguna línea con formato
- el mismo link repetido, que queda con la fecha más vieja

**La escritura**, con un vault en `tmp_path`:

- 3 links entran como 3 notas `partial` con sus fechas
- el comentario queda en `summary` y en `body`
- un link que ya está en el vault se cuenta en `already` y **no** se reescribe
  (verificado por mtime, no por contenido)
- un link con entrada en la cola creada **durante** la corrida se cuenta en
  `already` y no se escribe dos veces
- un link con entrada vieja en la cola pero **sin nota en el vault** se
  escribe: la nota borrada a mano no bloquea la reimportación
- los índices se reconstruyen **una sola vez** (contando llamadas)
- una nota que no se puede escribir no aborta las demás
- nada se escribe fuera de `oknowledge/`, con `attachments/` y `links/`
  apuntados a otro lado por un symlink

**El arreglo de la fecha**:

- una nota parcial de 2019 que se analiza conserva `saved: 2019-07-18`
- un `--reprocess` de una nota terminada conserva su fecha
- una nota nueva, sin nada en disco, se fecha hoy

**`retry --limit N`**:

- con 5 pendientes y `--limit 2`, se terminan 2 y quedan 3
- el orden es de lo más nuevo a lo más viejo
- una entrada que ya estaba saldada no consume cupo
- sin `--limit`, el comportamiento de hoy no cambia

Como en el resto del proyecto: ningún test toca la red, la suite corre con
`-W error`, y los mutantes de cada guard nuevo tienen que morir.
