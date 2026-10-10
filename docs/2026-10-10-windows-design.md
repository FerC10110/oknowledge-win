# La edición para Windows

El mismo oknowledge, para alguien que no tiene Omarchy ni Hyprland: se instala
con `uv`, se usa desde el navegador, y la caja de pegar un link —  que en Linux
vive en el panel de la barra — pasa a estar en la página.

Es un fork, decidido a propósito: este repo no puede romper el de Linux. El
precio es que un arreglo hay que traerlo, y para eso `origin` apunta al repo
original, así que `git pull origin feat/mentions-search` trae los arreglos en
lugar de obligar a escribirlos dos veces.

## Lo que ya es portable, que es casi todo

El pipeline, el vault y su frontmatter, la biblioteca web, los trece
proveedores, el `.env`, `yt-dlp`, y los dos motores locales: `opencode` y
`ollama` tienen build de Windows. Todo el código usa `pathlib`, no concatena
rutas con `/`, y los 1692 tests pasan.

## Los cinco puntos que no lo son

| Qué | Hoy | En Windows |
|---|---|---|
| El candado de la cola | `fcntl.flock` | no existe |
| Las rutas | `$XDG_STATE_HOME`, `~/.config` | `%LOCALAPPDATA%`, `%APPDATA%` |
| Los permisos | `chmod 600` | no hace nada |
| El idioma de la interfaz | el archivo compartido de Omarchy | no existe |
| Pegar un link | el panel de la barra | no hay panel |

### A. El candado

Es lo único que no es un detalle. `queue.lock()` garantiza dos cosas: que un
link no se procesa dos veces, y que **un proceso que se muere no deja el link
trabado para siempre** — porque el candado pertenece al archivo abierto y el
kernel lo suelta solo. No hay timeout que adivinar ni corrida muerta que
parezca ocupada.

`msvcrt.locking` tiene esa misma propiedad: se suelta cuando se cierra el
handle. Así que el contrato se mantiene. La diferencia está en el sondeo.

Un módulo nuevo, `locking.py`, con dos funciones y dos implementaciones:

```python
def take(fd) -> bool    # exclusivo, sin esperar. False si otro lo tiene
def probe(fd) -> bool   # True si otro lo tiene ahora mismo
```

| | POSIX | Windows |
|---|---|---|
| `take` | `flock(LOCK_EX \| LOCK_NB)` | `msvcrt.locking(LK_NBLCK, 1)` sobre un byte |
| `probe` | `flock(LOCK_SH \| LOCK_NB)` | toma el exclusivo y lo suelta en el acto |

`msvcrt` **no tiene modo compartido**, y de ahí sale la única diferencia de
comportamiento real de todo este diseño: en Windows, sondear un link lo toma
por un instante. Si otro proceso intenta tomarlo justo en ese microsegundo,
va a creer que está ocupado y va a saltear el link, que queda para la próxima
corrida. Es el lado seguro del error: nunca procesa dos veces, a veces
posterga. Un `status` concurrente con un `retry` es el caso donde pasa.

Dos detalles que el código tiene que respetar: el sondeo abre el archivo
`O_RDWR` y no `O_RDONLY`, porque en Windows no se puede lockear un handle de
sólo lectura; y `msvcrt.locking` necesita que el archivo tenga al menos el
byte que se lockea, así que el candado se crea con un byte escrito.

### B. Las rutas

Un módulo `places.py` con las dos preguntas que hoy están repartidas:

| | Linux | Windows |
|---|---|---|
| el config | `~/.config/oknowledge/` | `%APPDATA%\oknowledge\` |
| el estado: cola, candados, caché de modelos, trazas | `$XDG_STATE_HOME/oknowledge/` | `%LOCALAPPDATA%\oknowledge\` |

Las variables `XDG_*` se siguen respetando si están puestas: el mismo código
corre en los dos sistemas y los tests no necesitan dos caminos.

Y un aviso que hace falta sí o sí: `vault = "C:\Users\fer\vault"` **no es TOML
válido** (`\U` es un escape). El `ConfigError` tiene que decir que se escribe
con `/` o con comillas simples, porque es el primer error que va a cometer
todo el mundo.

### C. Los permisos

`chmod(0o600)` en Windows no falla: no hace nada. Eso deja dos mentiras que
hay que apagar:

1. `config.save()` y `env.create()` prometen un archivo que sólo vos podés
   leer. En Windows eso lo da la ACL de tu carpeta de perfil, no el modo. El
   código llama a un `only_you(path)` que en POSIX hace el `chmod` y en
   Windows no hace nada, y el comentario dice por qué.
2. `env.exposed()` compara `st_mode & 0o077`, y Windows informa `0o666` en
   todo. Avisaría "cualquiera puede leer tu `.env`" para siempre, lo cual es
   un aviso falso, que es peor que ninguno. En Windows contesta `False`, y la
   página, en lugar de hablar de `chmod`, dice dónde está el archivo.

### D. El idioma de la interfaz

Hoy sale de `~/.config/omarchy/plugin-language.json`, compartido con los otros
plugins. Acá no hay otros plugins: pasa a `[web] language` en el propio
`config.toml`, que el selector de Ajustes escribe. El `[ai] language` del
resumen no se toca: son dos ejes distintos y ya lo eran.

### E. La caja de pegar un link, en la página

Lo que reemplaza al panel. En el encabezado, al lado del buscador:

```
  oknowledge   [ buscá en tu biblioteca      ]   Categorías · Reproceso · Ajustes
               [ https://…                   ]   [Completo] [Resumen]
```

- `POST /add` con la URL y el modo. Valida con `normalize()` y `is_search_url()`
  — lo mismo que el panel valida hoy en `LinkModel.js` — encola, y corre el
  pipeline en una tarea de fondo, igual que `/retry`.
- Contesta 303 a la biblioteca con un aviso: encolado, ya lo tenés, o no es un
  link. La nota aparece cuando termina; mientras tanto la tarjeta existe en
  estado pendiente y el ↻ gira, que es maquinaria que ya está.
- Dos botones y no uno, porque `default_content` es una preferencia y esto es
  una decisión por link: es la misma elección que ofrece el panel.
- A ancho de celular la caja toma su propia línea, con los botones debajo.

## Lo que este diseño no hace

- **No hace un .exe.** Con `uv` no hace falta: `uv` instala Python solo. Un
  instalador firmado es otra decisión (y cuesta plata al año).
- **No hace un ícono en la bandeja** ni un atajo global. La caja en la página
  cubre el caso, y una app de bandeja es otra tecnología y otro proyecto.
- **No toca el vault ni el formato de la nota.** Una nota escrita en Windows
  se lee igual en Linux, y al revés: es el mismo Obsidian.
- **No agrega dependencias.** `msvcrt` es de la biblioteca estándar.

## Lo que no se puede probar acá, y hay que decirlo

Este diseño se escribe en una máquina con Linux. El código de Windows se
escribe contra la semántica documentada de `msvcrt.locking` y se prueba con un
`msvcrt` falso inyectado, lo que prueba la lógica y **no** el sistema
operativo. La prueba de verdad — que el candado se suelte cuando un proceso se
muere de verdad, que las rutas caigan donde van — necesita una máquina con
Windows. Hasta que alguien corra eso, el estado honesto es "escrito con
cuidado, sin probar en el sistema real".

Los 45 usos de `chmod` que hay en los tests para simular "esto no se puede
escribir" tampoco funcionan en Windows. Se marcan con `pytest.mark.skipif`
sobre `os.name`, no se borran: en Linux siguen siendo la prueba que son.

## Cómo se verifica

1. **Los 1692 tests que ya existen siguen pasando** en Linux. El fork no es
   una excusa para romper nada.
2. **Un test de contrato del candado**, el mismo para las dos
   implementaciones: tomar dos veces falla, sondear un libre dice libre,
   sondear un tomado dice tomado, y cerrar el handle lo suelta.
3. **Las rutas**, con y sin las variables de entorno, en los dos modos.
4. **El `.env` en Windows no avisa de más**: con un archivo 0o666 simulado,
   `exposed()` contesta False y la página no habla de `chmod`.
5. **Un `vault` con backslashes** da un `ConfigError` que dice cómo escribirlo.
6. **La caja de pegar**: una URL buena encola y corre; una vacía, una que no es
   URL y una búsqueda de Google no encolan nada; un link que ya está no se
   procesa dos veces.
7. **Mutación sobre todo lo nuevo**, como en el resto del proyecto.

## Cómo se corre

```
uv run oknowledge serve
```

`uv` baja Python y las dependencias solo. Para tenerlo como comando suelto:

```
uv tool install .
oknowledge serve
```
