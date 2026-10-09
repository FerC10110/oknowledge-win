# Trazas del pipeline, el motor en la nota, y elegir modelo de una lista

Tres pedidos que comparten una raíz: hoy el pipeline sabe cosas que nunca
cuenta. Qué está haciendo mientras tarda, qué modelo contestó, qué modelos hay
disponibles. Las tres se resuelven haciendo visible algo que ya existe adentro.

## Lo que ya está y lo que falta

| Lo que se quiere | Lo que ya existe | Lo que falta |
|---|---|---|
| Ver qué hace `retry` por atrás | `retry()` acepta `on_step` y llama una vez por link terminado; `Result` trae `id`, `url`, `status`, `engine`, `error`, `warnings` | Nada avisa *dentro* de un link. `add()` es una caja cerrada entre que arranca y que termina |
| Ícono del motor en la tarjeta | `analyze_with_chain()` devuelve qué motor contestó, y ese valor ya viaja hasta `_save()` | El motor se descarta al escribir: no está en `FRONTMATTER_ORDER` ni en la cola. El modelo no se devuelve en absoluto |
| Elegir modelo de una lista | La página de ajustes ya tiene un campo de texto por motor (`{{ name }}_model`) | Ningún motor sabe enumerar sus modelos |

Tres hechos medidos en esta máquina, que mandan sobre el diseño:

- `opencode models` responde al instante y lista 11 modelos, con salida de una
  línea por modelo.
- `ollama` los lista por `GET {url}/api/tags`, pero acá el servicio está
  `inactive`: un diseño que lo consulte y espere cuelga la página.
- Las **1182 notas que ya existen no tienen de dónde sacar el motor**. No se
  guardó nunca y no se puede deducir. Van a mostrar el ícono vacío para
  siempre, salvo que se las reanalice.

## A. Trazas del pipeline

### El paso

Un `Step` es un dataclass plano, sin comportamiento:

```python
@dataclass
class Step:
    link: str          # el id del link
    name: str          # "find" | "extract" | "analyze" | "cover" | "save"
    state: str         # "start" | "ok" | "fail"
    seconds: float     # 0.0 en "start"
    engine: str = ""   # solo en los pasos "analyze", uno por motor probado
    detail: str = ""   # una línea: tamaño, tipo, el motivo de la falla
```

### Dónde se emiten

En `_process()`, que es donde están los límites reales. Un `start` y un cierre
(`ok` o `fail`) por paso:

| Paso | Qué lo rodea | Qué dice el `detail` |
|---|---|---|
| `find` | `find_note()` | si había nota, y su estado |
| `extract` | `extract(url)` | tipo de página, palabras, bytes |
| `analyze` | **cada vuelta** del `for` de `analyze_with_chain()` | el modelo; al fallar, el motivo |
| `cover` | `download_cover()` | si bajó algo y cuánto |
| `save` | `_save()` | la ruta escrita |

El paso `analyze` se emite **por motor probado**, no por link: con una cadena
de dos, un link que falla en el primero y sale bien en el segundo muestra dos
líneas. Eso es justo lo que no se ve hoy.

### Una traza nunca cuesta un link

Es la regla de todo el módulo y acá es más fácil de romper que en ningún otro
lado, porque el que traza es código nuevo en el camino crítico. Dos defensas:

1. `add()` y `retry()` reciben `trace: Callable[[Step], None] | None = None`.
   Con `None` no se arma ni un objeto: el costo de no usarlo es una comparación.
2. Toda llamada al tracer pasa por un envoltorio que traga cualquier
   excepción, igual que `_announce()` hace hoy con `on_step`. Un tracer roto
   deja de informar; nunca tira un link.

El reloj es `time.monotonic()`, no el de pared: un ajuste de hora en medio de
un lote de una hora no puede dar duraciones negativas.

### El prompt y la respuesta, a archivo

Es lo único que sirve cuando el análisis no falla pero sale mal, y es también
lo único de este diseño que puede llenar un disco. Por eso:

**Apagado por defecto.** Un `[debug] trace = false` en `config.toml`, más una
casilla en la página `/retry` que lo prende **para ese lote y nada más**. Un
lote de 50 links guarda 50 archivos; prenderlo para siempre guardaría 1164.

**Dónde:** `$XDG_STATE_HOME/oknowledge/trace/<fecha-hora>/<link_id>.md`, una
carpeta por corrida. Fuera del vault a propósito: son descartables y no tienen
por qué sincronizarse con Obsidian ni aparecer en una búsqueda.

**Qué hay adentro:** la URL, el motor y el modelo, el prompt tal cual se mandó,
la respuesta cruda, y el resultado de parsearla. En Markdown con los bloques
en ``` para que se lea en el mismo Obsidian si se la copia.

**Cuánto:** tope de 256 KB por archivo, cortando por el medio del prompt (la
cabeza y la cola son lo que se mira) con una marca de cuánto se sacó. Y una
poda al arrancar cada corrida que deja las últimas 10 carpetas, con la misma
forma que `import_file.sweep()`: nunca levanta, es tarea de limpieza.

**Qué contiene:** el texto completo de tus páginas. Es tuyo y queda en tu
disco, pero conviene decirlo en la propia página: es contenido, no metadatos.

### Cómo llega a la página

Hoy `Progress` guarda tres enteros bajo un lock (`web/batch.py`). Se le agrega
una lista de líneas acotada — las últimas 200, un `deque(maxlen=200)` — que el
callback de trazas va llenando. Acotada porque un lote de 1164 links son unas
6000 líneas y la página las manda enteras en cada refresco.

La página `/retry` ya se refresca sola con `REFRESH`. Debajo de la barra de
progreso va la lista, lo más nuevo arriba. Sin JavaScript nuevo: el refresco
que ya existe la trae.

Lo que se vería:

```
 24/50   ⏳  youtube.com/watch?v=…
         extract    ok     1.2 s   youtube · 11.482 palabras
         analyze    fail   8.0 s   opencode/ling-3.1-flash-free · Upstream request failed
         analyze    ok    14.7 s   ollama/qwen2.5:7b
         save       ok     0.1 s   links/como-funciona-el-mtr.md
 23/50   ✓   Cómo funciona el MTR de Hong Kong            opencode    18.4 s
 22/50   ⚠   youtube.com/shorts/KLgx…                                  0.8 s
         el video no tiene ni descripción ni subtítulos
```

## B. El motor y el modelo en la nota

### Los campos

Dos, no uno: el ícono sale del motor y el tooltip del modelo, y meterlos en un
solo string obligaría a partirlo en cada lectura.

```python
engine: str = ""   # "opencode" | "ollama" | "api"
model: str = ""    # "opencode/ling-3.1-flash-free", "qwen2.5:7b", …
```

En `FRONTMATTER_ORDER` van entre `content` y `status`, que es donde están los
demás metadatos de cómo se hizo la nota. Vacíos se omiten, como `collections`:
las 1182 notas viejas no crecen ni un byte.

### Quién los llena

`analyze_with_chain()` hoy devuelve `(Analysis, nombre)`. Pasa a devolver
también el modelo, que el motor ya tiene en `self.model`. De ahí sigue el
camino que el nombre ya hace hasta `_save()`.

Un reanálisis los pisa con los nuevos, que es lo correcto: dicen quién hizo el
contenido que está ahí ahora. **No** se preservan como `collections` o
`mentions_extra`, porque no son del usuario.

### En la tarjeta

Un SVG dibujado por motor, al lado del favicon, con `title` y `aria-label`
= `"opencode · ling-3.1-flash-free"`. Dibujado y no emoji, por lo mismo que el
disquete y la flecha de reintentar: un emoji depende de una fuente que el
navegador puede no tener, y en esta sesión ya pasó dos veces.

Tres íconos, uno por motor, no uno por proveedor: `api` es un solo motor
aunque apunte a OpenAI o a Anthropic. El proveedor va en el tooltip.

Una nota sin `engine` **no dibuja nada**. No un signo de pregunta ni un hueco:
1182 de 1184 notas están en ese caso y un ícono de "no sé" repetido mil veces
es ruido, no información.

## C. Elegir modelo de una lista

### Cada motor se enumera a sí mismo

Un método nuevo, opcional, con una sola promesa: **nunca levanta y nunca
cuelga**. Devuelve `[]` ante cualquier problema.

```python
def models(self) -> list[str]:
```

| Motor | Cómo | Cuándo da `[]` |
|---|---|---|
| opencode | `opencode models`, timeout 5 s | el binario no está, o tardó |
| ollama | `GET {url}/api/tags`, timeout 2 s | el servidor no corre (el caso de hoy) |
| api | `GET {base_url}/v1/models`, timeout 5 s | sin key, o el proveedor no lo expone |

### El control

El campo de texto que ya existe pasa a ser `<input list="models-opencode">`
con su `<datalist>` al lado. Te ofrece la lista y te deja escribir igual, que
es exactamente lo que pediste para cuando no se pueda enumerar. Es el mismo
patrón que ya usan las categorías y las colecciones en `item.html`: nada
nuevo que aprender ni que mantener.

### Cuándo se pregunta

**No al cargar la página.** Tres motores con sus timeouts son hasta 12
segundos de espera para abrir Ajustes, y el caso de hoy — ollama apagado — es
justo el lento. En cambio: un botón **Buscar modelos** por motor, que consulta
ese motor y vuelve a dibujar la página.

Lo que encuentra se guarda en `$XDG_STATE_HOME/oknowledge/models.json`, así la
próxima vez el `<datalist>` ya está lleno sin preguntarle a nadie. Con la
fecha de cuándo se buscó, mostrada al lado del botón: una lista de hace un mes
es una lista, no una mentira, siempre que diga que es de hace un mes.

## Lo que este diseño no hace

- **No paraleliza nada.** `retry()` sigue siendo un `for` secuencial. Las
  trazas lo van a dejar obvio, que es distinto de arreglarlo.
- **No rellena las notas viejas.** No hay dato del cual sacarlo.
- **No manda las trazas a ningún lado.** Quedan en tu disco.
- **No agrega logging.** El pipeline sigue sin `logging`: el tracer es un
  callback explícito que el que llama provee, y así se puede probar.

## Cómo se verifica

1. **Las trazas no cuestan un link.** Un test con un tracer que levanta en
   cada paso: la nota se escribe igual y el `Result` es idéntico al de una
   corrida sin tracer. Es la prueba que justifica todo el envoltorio.
2. **Un link que cae al segundo motor emite dos pasos `analyze`**, el primero
   `fail` con su motivo y el segundo `ok`, con el modelo de cada uno.
3. **El archivo de traza respeta el tope**: un prompt de 1 MB queda en 256 KB
   con la marca de lo recortado, y el principio y el final intactos.
4. **La poda deja 10 carpetas** y no levanta con una carpeta que no se puede
   borrar.
5. **El motor y el modelo sobreviven una ida y vuelta** por `write_note` /
   `read_note`, y una nota sin ellos se lee con los dos en `""`.
6. **Un reanálisis los pisa**; `collections` y `mentions_extra` no.
7. **La tarjeta de una nota sin motor no dibuja ícono**, y una con motor lo
   dibuja con el modelo en el `title`.
8. **`models()` devuelve `[]` con el servidor apagado** y no tarda más que su
   timeout — con ollama apagado, que es el estado real de esta máquina.
9. **Ajustes abre sin consultar a ningún motor**: un test que falla si abrir
   la página lanza un subproceso o toca la red.
10. Mutación sobre cada test nuevo, como siempre.
