# Acciones sobre una idea: que el segundo cerebro piense con vos

**Fecha:** 2026-10-12 · **Rama:** `feat/idea-actions`

Tercer paso del segundo cerebro. La sección de ideas ya guarda lo que se te
ocurre y el modelo le pone nombre, etiquetas y puntos. Lo que falta es que te
ayude a pensarla:

> "Quiero agregar acciones: buscar si la idea ya existe en internet o hay
> similares. Buscar mejoras o ampliar la idea"
>
> "buscar entre los links guardados filtrando por categoría"

Cuatro botones en la página de una idea, y cada uno deja su respuesta escrita
en la nota de la idea, al lado de tu texto y sin tocarlo.

## Decisiones tomadas

| Pregunta | Respuesta |
|---|---|
| ¿Quién busca en internet? | el motor, no la app |
| ¿Dónde queda lo que devuelve cada acción? | una sección propia en la nota; pedirla de nuevo reemplaza sólo esa sección |
| ¿Los links que sirven se suman solos? | no: se sugieren, cada uno con un botón **Sumar** |
| ¿Entre qué links busca? | los de la categoría que elegís al pedirlo, o todos |
| ¿Cuántas acciones? | cuatro: ¿Ya existe?, Mejorar, Ampliar, Links que sirven |
| ¿Cómo entra la búsqueda en el contrato de los motores? | un método aparte, `search(prompt) -> str`, sólo en los motores que pueden |
| ¿Qué corridas de opencode van encerradas en `bwrap`? | todas; sin `bwrap`, opencode no corre |

## Hechos medidos

Medido el 2026-10-12 en esta máquina, con opencode 1.18.35, en directorios
descartables.

| Hecho | Qué implica |
|---|---|
| `opencode run --pure` con `opencode/mimo-v2.6-flash-free` usó su herramienta `websearch` y devolvió apps reales con URL | opencode busca sin configurar nada |
| `opencode/ling-3.1-flash-free`, el modelo de tu cadena, devolvió 429 *Endpoint is unavailable* en las dos pruebas | la búsqueda puede fallar por el modelo, y el aviso tiene que decirlo |
| Con `--format json`, cada herramienta usada llega como un evento `{"part": {"type": "tool", "tool": "websearch", "state": {"status": "completed"}}}` y el texto como `{"part": {"type": "text", "text": …}}` | la app puede **comprobar** que el modelo buscó, en vez de creerle |
| opencode ejecuta bash cuando el prompt se lo pide (`uname -a` corrió), también con `--agent plan` | hoy cada análisis de link corre un agente con bash y red, y en su prompt va el texto de una página de internet |
| Cualquier config que restrinja herramientas o permisos (`OPENCODE_CONFIG_CONTENT`, un `opencode.json` con `permission`, un agente en `.opencode/agent/`) hace que el servicio responda 403 *"OpenCode's free tier can only be used from within OpenCode"* | opencode no se puede restringir desde adentro sin perder el acceso gratis |
| Un `opencode.json` vacío (`{}`) no dispara el 403 | lo que se castiga es la restricción, no el archivo |
| Encerrado en `bwrap`, con `/home` vacío salvo las cuatro carpetas de opencode, opencode respondió, buscó y no vio ni `~/Projects` ni `~/.config/oknowledge` | el encierro se hace desde afuera y el acceso gratis sigue andando |
| Para que haya red adentro hay que montar `/run/systemd/resolve` (de ahí apunta `/etc/resolv.conf`) | sin eso, opencode dice *"Cannot connect to API"* |
| El contrato de hoy es `complete(prompt: str) -> str`, igual en todos los motores | `ai/base.py` |
| La sección de tu texto en una idea corre hasta el final de la nota (`mine_to_end`) | `vault.py`, `_split_body` |
| `complete_idea()` llama al modelo fuera del lock, relee la idea bajo el lock y escribe sólo sus campos | `pipeline.py` |
| La cola de tareas es `BackgroundTasks`, y el estado en memoria del proceso (`Batch`) se dibuja en cada página | `web/app.py` |

## A. El encierro de opencode

Todas las corridas de opencode pasan por `bwrap`: el análisis de cada link,
las fichas, el completado de ideas y las cuatro acciones nuevas. Es una sola
función, `sandboxed(argv, cwd) -> list[str]`, en `ai/opencode.py`, que
devuelve el argv envuelto:

```
bwrap --unshare-all --share-net --die-with-parent
      --ro-bind /usr /usr  --symlink usr/bin /bin
      --symlink usr/lib /lib  --symlink usr/lib /lib64
      --ro-bind /etc /etc  --ro-bind-try /run/systemd/resolve /run/systemd/resolve
      --proc /proc  --dev /dev  --tmpfs /tmp  --tmpfs /home
      --clearenv --setenv PATH … --setenv HOME … --setenv LANG …
      --bind <carpetas propias> <donde opencode las busca>  (data, config, cache, state)
      --ro-bind <carpeta del binario de opencode> <la misma>
      --bind <directorio temporal> /work  --chdir /work
      --setenv HOME <tu home>
      <binario de opencode, resuelto> run --pure …
```

- **Las carpetas de opencode** salen de `XDG_DATA_HOME`, `XDG_CONFIG_HOME`,
  `XDG_CACHE_HOME` y `XDG_STATE_HOME`, con sus valores por omisión, más
  `/opencode`. Se crean antes de montarlas si no existen.
- **El binario** se resuelve con `shutil.which` y `os.path.realpath`. Así un
  shim de mise apunta al ejecutable de verdad, y se monta su carpeta sólo si
  no cae ya bajo `/usr`.
- **Lo que queda afuera:** tu vault, tus proyectos, `~/.config/oknowledge`
  con el `.env` de las API keys, `~/.ssh` y todo lo demás de tu home.
- **Lo que queda adentro:**
  - la red, porque sin red no hay modelo;
  - las carpetas de opencode, que guardan su historial de sesiones.

  Un bash que obedezca a una página puede leer ese historial y mandarlo
  afuera. Ese historial es texto que la app ya le pasó al modelo; no hay
  secretos tuyos.
- **Sin `bwrap`:** `complete()` y `search()` levantan `EngineError` con
  *"opencode needs bubblewrap to run sandboxed: install it (pacman -S
  bubblewrap)"* y la cadena sigue con el motor siguiente, como con cualquier
  otro motor que falla.
- **El fork de Windows** (`oknowledge-win`) no tiene `bwrap`. Este cambio no
  se le aplica tal cual, y queda anotado para cuando se decida ese merge.

## B. Un método aparte para buscar

`complete(prompt) -> str` no cambia. Se agrega:

```python
class Engine(Protocol):
    name: str
    searches: bool          # whether this engine can look things up on the web
    def complete(self, prompt: str) -> str: ...
    def search(self, prompt: str) -> str: ...   # only when searches is True
```

| motor | `searches` | cómo busca |
|---|---|---|
| `opencode` | `True` | la misma corrida encerrada, con `--format json`. La respuesta es el texto de los eventos `text`. **Si no hay ningún evento `websearch` o `webfetch` completado, levanta `EngineError("the model did not search the web")`**: un "no existe nada igual" sin haber buscado es peor que no contestar |
| `api`, protocolo `anthropic` | `True` | el mismo pedido con `"tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]`. La respuesta es la unión de todos los bloques `text`, porque con herramientas `content[0]` deja de ser el texto. Si no hay ningún bloque `web_search_tool_result`, el mismo `EngineError` |
| `api`, protocolo `openai` | `False` | — |
| `ollama` | `False` | — |
| `fake` | `True` | devuelve la respuesta siguiente de su lista, igual que `complete()` |

`search_with_chain(cfg, prompt, parse)` (y su par sin internet, `ask_with_chain`) recorre la cadena en tu orden y prueba sólo
los motores con `searches` en `True`. Si ninguno de la cadena busca, levanta
`AllEnginesFailed("no engine in the chain can search the web")` sin llamar a
nadie. `can_search(cfg) -> bool` dice lo mismo sin llamar a nadie, para la
página.

## C. Las cuatro acciones

| botón | `action` | motor | prompt | sección |
|---|---|---|---|---|
| ¿Ya existe? | `exists` | `search_with_chain` | `prompts/idea-exists.txt` | `## Ya existe` |
| Mejorar | `improve` | `complete` (la cadena de siempre) | `prompts/idea-improve.txt` | `## Mejoras` |
| Ampliar | `expand` | `complete` | `prompts/idea-expand.txt` | `## Ampliación` |
| Links que sirven | `links` | `complete` | `prompts/idea-links.txt` | `## Links que pueden servir` |

En inglés las secciones son `Already out there`, `Improvements`, `Expansion`
y `Links that may help`, igual que `HEADINGS` ya tiene las dos lenguas.

Cada prompt recibe el título, tu texto, las etiquetas y el resumen de la
idea, y pide JSON. La app valida ese JSON y escribe la sección; el modelo
nunca escribe markdown directo en la nota.

**¿Ya existe?**

```json
{"verdict": "exists | similar | new",
 "matches": [{"name": "…", "url": "https://…", "note": "en qué se parece"}],
 "difference": "en qué se diferencia la tuya"}
```

```markdown
## Ya existe

**Hay parecidas.** Buscado el 2026-10-12 con opencode/mimo-v2.6-flash-free.

- [Linkwise](https://linkwise.app/) — guarda links con resumen y los manda a Obsidian.
- [2Vault](https://chromewebstore.google.com/detail/…) — extensión que resume marcadores.

**Lo tuyo:** …
```

- Un `verdict` fuera de los tres vale `similar`.
- Una URL que no sea `http(s)` se descarta junto con su fila.
- Hay como mucho ocho filas.
- `new` sin filas se escribe *"No encontré nada igual."*
- La línea de fecha y motor está porque la respuesta envejece: lo que no
  existía en octubre puede existir en marzo.

**Mejorar** devuelve `{"items": [{"weak": "…", "fix": "…"}]}` y se escribe
como `- **{weak}** — {fix}`, con un máximo de ocho. **Ampliar** devuelve
`{"items": ["…"]}` (funciones, público, próximos pasos que no escribiste), con
un máximo de diez, una viñeta por ítem.

**Links que sirven**

1. Elegís una categoría en el selector, o *Todas*.
2. La app junta los candidatos del estante de **links**, no de ocio ni de
   ideas:
   - los de esa categoría;
   - menos los que ya están en `related`.
3. Los ordena por cuántas palabras comparten con la idea, contando título,
   texto y etiquetas, sin las palabras de menos de cuatro letras. Se queda con
   los **60** primeros.
4. Le pasa al modelo una línea por candidato:
   `id | título | categoría | resumen (hasta 200 caracteres)`.
5. El modelo devuelve `{"links": [{"id": "…", "why": "…"}]}`.
6. La app descarta todo id que no estaba entre los candidatos, se queda con
   diez como mucho y escribe:

```markdown
## Links que pueden servir

*Entre: Herramientas.*

- [[2026-10-02-rutina-de-fuerza]] — tiene la progresión de cargas que la idea necesita.
```

El wikilink usa el nombre del archivo del link **al momento de escribir**,
como `related`. Si después el link se renombra, la fila aparece apagada en la
página, igual que un relacionado que no resuelve. En este spec no hay repunte
para esta sección: es una sugerencia y se vuelve a pedir en un clic.

Si una categoría no tiene candidatos, no se llama al modelo y la sección
queda en *"No hay links en Herramientas que no estén ya relacionados."*

## D. La nota

`Note` gana `actions: dict[str, str]`: el markdown de cada sección, por
`action`, tal como está en el archivo. Se guarda el texto y no la estructura
por la misma razón que `my_note`: lo podés editar en Obsidian, y lo que
escribiste ahí tiene que sobrevivir a que la app relea y reescriba la nota.

- **Lugar:** después de los puntos y antes de las menciones, en el orden de la
  tabla de C. Tienen que ir antes de `Mi nota`, porque en una idea esa
  sección corre hasta el final.
- **Lectura:** `_split_body` reconoce estos encabezados **sólo en una idea**
  (el mismo `mine_to_end` que ya existe). En una ficha o un link, un
  `## Mejoras` escrito a mano sigue siendo parte del resumen, como hoy.
- **Escritura:** `render` escribe sólo las acciones que existen. Una idea sin
  acciones queda byte a byte como hoy.
- **Pedir de nuevo** reemplaza esa sola clave del dict. Tu texto, el título,
  las etiquetas, el resumen, los puntos, los relacionados, el estado y las
  estrellas no se tocan.

## E. El flujo

`POST /item/{id}/actions/{action}`, con `category` en el formulario sólo para
`links`:

1. Si `action` no es una de las cuatro, devuelve 404. Si la idea no existe,
   aviso `no-such-idea`.
2. Si es `exists` y `can_search(cfg)` es falso, aviso `cannot-search` y no se
   encola nada.
3. Encola `run_idea_action(cfg, idea, action, category)` en `BackgroundTasks`
   y anota `(idea, action)` como en curso en un registro en memoria, el mismo
   molde que `Batch`. Si esa misma acción ya estaba en curso, no encola otra.
4. Redirige a la idea con el aviso `thinking`: *"Thinking it over. Reload in
   a moment to read it."*

`run_idea_action` sigue el esqueleto de `complete_idea`:

1. Llama al modelo **fuera** del lock.
2. Toma el lock de la idea y la relee.
3. Si la idea ya no está, no escribe nada.
4. Si sigue, pone sólo `note.actions[action]` y la escribe.
5. No reconstruye el índice de ideas: el índice muestra título y resumen, y una acción no cambia ninguno de los dos.

Dos acciones distintas sobre la misma idea pueden correr juntas: cada una
relee bajo el lock y escribe sólo su clave, así que ninguna pisa a la otra.

**En la página**, debajo de los puntos, van los cuatro botones con su
sección. Cada botón:

- dice *Pedir de nuevo* cuando su sección ya existe;
- dice *pensando…* y queda apagado mientras su acción está en curso;
- en el caso de ¿Ya existe?, queda apagado cuando nadie de la cadena busca,
  con el título *"Ningún motor de tu cadena busca en internet: opencode o la
  API de Anthropic sí."*;
- si su última corrida falló, muestra debajo *"La última vez falló: …"* con el
  mensaje del motor. Ese mensaje sale del mismo registro en memoria y se borra
  cuando una corrida sale bien.

Cada fila de Links que pueden servir lleva el botón **Sumar**, que postea a
`POST /item/{link}/ideas`, la ruta que ya existe. Si el link ya está en
`related`, la fila dice *ya relacionado* en lugar del botón.

## Cuando algo falla

| Qué pasa | Qué se ve |
|---|---|
| Ningún motor de la cadena busca | ¿Ya existe? apagado con su explicación; las otras tres andan |
| No hay `bwrap` | opencode falla con el mensaje de instalación; si hay otro motor en la cadena, contesta ese |
| El modelo no buscó (opencode sin evento `websearch`) | *"La última vez falló: the model did not search the web"*; la sección anterior queda intacta |
| El modelo no contesta, o no contesta JSON | lo mismo: aviso debajo del botón, sección anterior intacta |
| El modelo inventa un id de link | se descarta esa fila |
| El modelo devuelve una URL `javascript:` o `file:` | se descarta esa fila |
| Borraste la idea mientras el modelo pensaba | no se resucita |
| Editaste el texto mientras el modelo pensaba | tu texto queda; la acción escribe sólo su sección |
| Dos clics al mismo botón | una sola corrida |
| El servidor se reinicia a mitad de camino | la corrida se pierde, sin nada a medio escribir; el botón vuelve a estar disponible |
| Editaste a mano una sección en Obsidian | se lee y se muestra tal cual hasta que la pidas de nuevo |

## Lo que este diseño no hace

- **Ampliar y Mejorar no buscan en internet.** Piensan sobre tu texto.
- **El modelo nunca escribe tu texto.** Las mejoras son propuestas al lado.
- **No hay historial de respuestas:** pedir de nuevo reemplaza.
- **Las sugerencias de links no se repuntan** cuando un link se renombra.
- **Links que sirven no busca en Ocio ni en otras ideas.**
- **No se elige qué motor busca.** Busca el primero de tu cadena que puede.
- **La API con protocolo `openai` no busca,** aunque algunos proveedores
  tengan su propia variante. Cada una tiene otro formato, y hoy tu cadena es
  sólo opencode.

## Cómo se verifica

TDD con mutación sobre todo lo nuevo, como el resto del repo. Nada de los
tests toca la red ni lanza opencode de verdad.

1. **El encierro:**
   - El argv que devuelve `sandboxed()` monta `/home` vacío y no monta el
     vault, `~/.config/oknowledge`, `~/.ssh` ni `~/Projects`.
   - Monta las cuatro carpetas de opencode y `/run/systemd/resolve`.
   - Sin `bwrap` en el PATH, `complete()` levanta el `EngineError` de
     instalación **sin** lanzar opencode.
   - `complete()` y `search()` de opencode pasan por `sandboxed()`; `models()` no, porque no lleva prompt.
2. **La búsqueda de opencode:**
   - Con eventos JSON grabados, devuelve el texto.
   - Sin evento `websearch` o `webfetch` completado, levanta el error.
   - Con un evento `error`, levanta el error con el mensaje.
3. **La búsqueda de la API:**
   - Con una respuesta grabada de varios bloques, une los `text`.
   - Sin `web_search_tool_result`, levanta el error.
   - Pide la herramienta sólo en `search()`, nunca en `complete()`.
   - La key nunca aparece en un mensaje de error.
4. **La cadena:**
   - `search_with_chain` salta los motores que no buscan.
   - Con una cadena sin buscadores, no llama a nadie.
   - `can_search` coincide con lo anterior.
5. **Las secciones:**
   - Ida y vuelta de cada una.
   - Una idea sin acciones queda byte a byte igual.
   - Un `## Mejoras` en una ficha sigue siendo parte del resumen.
   - Tu texto con un `## Mejoras` adentro sigue siendo tuyo, porque `Mi nota`
     va después.
   - Una sección editada a mano sobrevive a otra acción.
6. **Cada acción:**
   - Escribe sólo su clave.
   - No toca texto, título, etiquetas, relacionados, estado ni estrellas.
   - Una idea borrada no vuelve.
   - Con un JSON malo, la nota queda igual.
   - Las URLs que no son `http(s)` y los ids inventados se descartan.
   - Respeta los topes de 8, 10 y 60.
   - Una categoría sin candidatos no llama al modelo.
7. **La página:**
   - Los botones dicen *pensando…* mientras corren.
   - ¿Ya existe? aparece apagado sin buscadores.
   - El error de la última corrida se ve y se borra al salir bien.
   - **Sumar** postea a la ruta existente.
   - Un link ya relacionado no ofrece **Sumar**.
   - El meta-test de rutas de escritura cubre la ruta nueva.
8. **En vivo, en un vault descartable:**
   - ¿Ya existe? con la cadena real, encerrada, devuelve URLs reales.
   - Un prompt que pide `ls ~/Projects` no ve nada.

## Después de esto

Con esto se cierra el segundo cerebro tal como se planteó: guardar links,
fichas de ocio, ideas, y que el modelo piense con vos sobre ellas. Lo que
quedó afuera arriba es lo siguiente si hace falta: que Ampliar también busque,
el repunte de las sugerencias, y la búsqueda para los proveedores `openai`.

## Revisión final (2026-10-12)

El revisor encontró que el encierro montaba las carpetas **reales** de
opencode: su config tiene plugins que corren sin encierro la próxima vez que
abrís opencode, y sus datos tienen todas tus sesiones. Ahora el encierro usa
un juego propio en `~/.local/share/oknowledge/opencode/{data,config,cache,state}`,
montado donde opencode las busca, y no pasa ninguna variable de entorno salvo
`PATH`, `HOME` y `LANG`. Medido: el acceso gratis anda igual con esas
carpetas vacías.

Lo que queda abierto: el encierro comparte la red de la máquina, así que
desde adentro se llega a `localhost` (este servidor, ollama) y al socket
abstracto de X11.
