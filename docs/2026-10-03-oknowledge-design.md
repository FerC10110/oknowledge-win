# oknowledge: biblioteca de links con resumen automático

## Contexto

Guardo links en favoritos, en WhatsApp y en archivos de texto, y nunca vuelvo
a verlos. El problema no es guardarlos: es que lo guardado no dice nada. Una
URL suelta en un `links.md` no me recuerda de qué se trataba ni me deja
encontrarla seis meses después.

Quiero pegar un link y que el sistema lo entienda solo: que baje la página, la
resuma, le ponga una categoría y tags, y lo deje en un lugar donde después
pueda **hojear** y **buscar** por información, no por URL.

La información vive en mi vault de Obsidian
(`/home/fer/Documents/obsidian_vaults/fer`), como Markdown. El vault es la
única fuente de verdad: no hay base de datos escondida.

Este documento diseña la primera versión completa: el motor, el widget de
Omarchy y la interfaz web.

## Decisiones

- **El vault manda.** Todo lo que el sistema sabe está en archivos Markdown
  dentro del vault. Cualquier índice se reconstruye leyéndolo.
- **Una nota por link, más un índice por categoría** que el sistema regenera.
- **La IA inventa la categoría**, sin lista fija, pero recibe las categorías
  que ya existen y debe reutilizar una si encaja. La web permite renombrar y
  fusionar categorías: esa es la poda.
- **Los tags son libres**, de 3 a 8 por link, normalizados.
- **Sin API key obligatoria.** Tres motores de IA intercambiables —
  `opencode`, `ollama` y `api` — habilitados y ordenados por el usuario.
- **El contenido completo se guarda dentro de la nota** por defecto, y al pegar
  el link se puede elegir guardar sólo el resumen.
- **Nunca se pierde un link.** Si falla cualquier paso, la nota se crea igual,
  marcada como incompleta, y `retry` la completa después.
- **El sistema sólo escribe dentro de `oknowledge/`** y sólo en archivos que
  lleven el marcador `oknowledge: 1` en el frontmatter.
- **Interfaz moderna y minimalista, sin ruido.**
- **Código, nombres de archivo, claves de datos y textos de interfaz en
  inglés**, igual que mis plugins. El contenido generado — resumen, categoría,
  tags — sale en español.

## El repositorio

`/home/fer/Projects/oknowledge`, un solo repo con las dos mitades:

```
docs/                     este documento y los que vengan
src/oknowledge/           el paquete Python
  cli.py                  add · serve · reindex · retry · status
  extract/                article.py youtube.py github.py pdf.py social.py
  ai/                     opencode.py ollama.py api.py fake.py
  vault.py                la única capa que escribe Markdown
  prompts/analyze.txt
  web/                    FastAPI, plantillas y estáticos
plugin/                   el plugin de Omarchy (manifest.json, QML)
tests/
pyproject.toml
```

Dependencias del venv: `trafilatura`, `pypdf`, `fastapi`, `uvicorn`,
`httpx`, `pyyaml`, `tomli-w`. `yt-dlp` **no** se instala en el venv: se usa el
binario del sistema, que ya viene con Omarchy y se actualiza con él.

Durante el desarrollo,
`~/.config/omarchy/plugins/io.github.ferc10110.oknowledge` es un symlink a
`plugin/`, y `omarchy plugin validate` se corre sobre esa carpeta del repo.

## Arquitectura

Tres piezas, con una sola dirección de dependencia:

```
widget de Omarchy  ──llama──▶  CLI oknowledge  ──escribe──▶  vault
                                     │                         │
                                     └──sirve──▶ web ──lee─────┘
```

Nadie llama para atrás. El motor se usa y se prueba desde la terminal sin
levantar la shell ni el navegador.

### El CLI

Paquete Python `oknowledge`, instalado en un venv propio en
`~/.local/share/oknowledge/venv`. El plugin lo invoca por ruta absoluta, sin
depender del `PATH`.

| Comando | Qué hace |
|---|---|
| `oknowledge add <url> [--full\|--summary] [--engine <nombre>]` | procesa un link de punta a punta |
| `oknowledge serve [--port 8787] [--open]` | levanta la web |
| `oknowledge reindex` | reconstruye todos los índices leyendo el vault |
| `oknowledge retry [--all\|<id>]` | reintenta los links incompletos o fallidos |
| `oknowledge status [--json]` | qué hay en la cola, qué falló |

### Flujo de `add`

1. Normaliza la URL (quita `utm_*` y fragmentos) y calcula su `id`: los 12
   primeros caracteres del SHA-256 de la URL normalizada.
2. Si ya existe una nota con ese `id`, no duplica: avisa y sale, salvo
   `--reprocess`.
3. Toma un lock por `id` en `~/.local/state/oknowledge/locks/`.
4. Escribe la entrada de cola en `~/.local/state/oknowledge/queue/<id>.json`
   con estado `pending`.
5. Detecta el tipo por dominio y extensión y elige el extractor.
6. Extrae: texto, título, autor, fecha de publicación y portada.
7. Analiza con el primer motor disponible de la cadena.
8. Escribe la nota y regenera el índice de su categoría.
9. Marca `ok` y borra el lock.

Un proceso por link, sin demonio. Varios links pegados seguidos corren en
paralelo; el lock por `id` impide que el mismo entre dos veces.

### Extractores

| Tipo | `type` | Cómo |
|---|---|---|
| Artículo, blog, documentación | `article` | `trafilatura` sobre el HTML; portada de `og:image` |
| YouTube | `youtube` | `yt-dlp`: título, canal, descripción y transcripción automática si existe |
| Repositorio de GitHub | `github` | API pública: descripción, lenguaje, estrellas y README |
| PDF | `pdf` | `pypdf`, primeras 20 páginas |
| Redes sociales | `social` | mejor esfuerzo. Reddit vía su JSON público; X, Instagram y TikTok suelen bloquear: si no se puede leer, la nota queda con título y URL y estado `partial` |
| Cualquier otra cosa | `other` | `trafilatura` como último recurso |

Ningún extractor ejecuta JavaScript ni abre un navegador. Si una página lo
necesita, se guarda como `partial`.

## El vault

### Estructura

```
oknowledge/
  Redes.md                       ← índice de categoría, autogenerado
  Cocina.md
  links/
    2026-10-03-wireguard-vs-openvpn.md
    2026-10-02-fermentar-en-casa.md
  attachments/
    wireguard-vs-openvpn.jpg
```

El nombre de archivo de una nota es `YYYY-MM-DD-<slug del título>.md`. Si ya
existe, se le agrega `-2`, `-3`.

### Una nota

```markdown
---
url: https://arstechnica.com/...
title: WireGuard vs OpenVPN
category: Redes
tags: [vpn, privacidad, wireguard, kernel]
type: article
source: arstechnica.com
author: Dan Goodin
published: 2026-09-28
saved: 2026-10-03
cover: ../attachments/wireguard-vs-openvpn.jpg
content: full
status: ok
id: 9f2a1c4b8e07
oknowledge: 1
---

# WireGuard vs OpenVPN

Compara ambos protocolos en rendimiento, auditabilidad y facilidad de
configuración, y explica por qué el primero se volvió el default...

## Puntos clave

- WireGuard corre en el kernel, por eso...
- OpenVPN sigue ganando cuando...

## Contenido original

(el texto extraído, sólo si `content: full`)
```

Las claves del frontmatter van en inglés; los valores que genera la IA
—`category`, `tags`, el resumen y los puntos— salen en español.

| Clave | Valores |
|---|---|
| `type` | `article`, `youtube`, `github`, `pdf`, `social`, `other` |
| `content` | `full`, `summary` |
| `status` | `ok`, `partial`, `failed` |
| `oknowledge` | `1`: versión del formato. Su ausencia protege la nota |

### El índice de categoría

Se regenera entero cada vez que una nota de esa categoría cambia, y también
con `reindex`. Lleva arriba un aviso de que no se edita a mano.

```markdown
---
oknowledge: 1
kind: index
category: Redes
---

# Redes · 12 links

<!-- Generado por oknowledge. Los cambios a mano se pierden. -->

- [[2026-10-03-wireguard-vs-openvpn|WireGuard vs OpenVPN]]
  `#vpn #privacidad` — Compara ambos protocolos en rendimiento...
- [[2026-09-28-tuneles-ssh|Túneles SSH]]
  `#ssh #redes` — Port forwarding local, remoto y dinámico...
```

### Editar a mano es parte del diseño

`reindex` lee el frontmatter de cada nota y reconstruye los índices desde
cero. Si cambio `category` o `tags` en Obsidian, el índice se acomoda. Si borro
una nota, desaparece de su índice. El usuario tiene la última palabra sobre la
clasificación.

### La regla de seguridad

El sistema sólo escribe dentro de `oknowledge/`, y sólo en archivos cuyo
frontmatter tenga `oknowledge: 1`. Un archivo sin ese marcador no se modifica
ni se borra jamás, aunque esté en esa carpeta.

## La IA

Una interfaz, `analyze(text, meta) -> Analysis`, con cuatro implementaciones.
`Analysis` tiene `title`, `summary`, `points`, `category` y `tags`.

| Motor | Cómo | Sale de la máquina | Necesita |
|---|---|---|---|
| `opencode` | `opencode run -m <modelo> --pure` en un directorio temporal vacío | sí, al gateway de opencode | nada |
| `ollama` | POST a `/api/chat` en `localhost:11434`, con salida JSON forzada | no | `ollama serve` y un modelo bajado |
| `api` | proveedor y modelo configurables | sí, al proveedor | una API key |
| `fake` | devuelve JSON fijo | no | sólo para tests |

- **La cadena es a la vez interruptor y prioridad.** `chain = ["opencode"]`
  usa sólo ese; `["ollama", "opencode"]` intenta local primero y cae al otro.
  Lo que no está en la lista no se usa aunque esté configurado.
- `--engine <nombre>` fuerza uno para un link puntual.
- Si `ollama` está en la cadena, instalado y apagado, el CLI lo levanta antes
  de fallar.
- La API key nunca se escribe en el vault ni en el repo: vive en
  `~/.config/oknowledge/config.toml` con permisos `600`, o se lee de la
  variable de entorno que indique `key_env`.

### El prompt

Vive en `src/oknowledge/prompts/analyze.txt`, un archivo de texto fuera del
código, para poder afinarlo sin tocar Python. Recibe el texto extraído, los metadatos y **la lista
de categorías que ya existen**, con la instrucción de reutilizar una si encaja
y de inventar sólo si ninguna sirve. Pide un JSON con esta forma:

```json
{
  "title": "...",
  "summary": "5 a 10 líneas, en español",
  "points": ["...", "..."],
  "category": "...",
  "tags": ["...", "..."]
}
```

### Validación

Nunca se confía en la salida:

- Se parsea el JSON y se valida contra el esquema.
- Los tags se pasan a minúsculas, se les quitan espacios y acentos, se
  deduplican y se recortan a 8.
- La categoría se compara contra las existentes sin distinguir mayúsculas ni
  acentos, para no crear "Redes" y "redes".
- Si el JSON es inválido, un reintento con instrucción más estricta. Si falla
  de nuevo, la nota se guarda con `status: partial`.
- Si el texto excede el límite del modelo, se recorta por el principio y la
  nota lo deja anotado.

## El widget de Omarchy

Plugin `io.github.ferc10110.oknowledge`, con `kinds: ["service", "bar-widget"]`:
el *service* tiene la cola y el estado, el *bar widget* lo muestra.

- Al abrir el panel **lee el portapapeles**: si hay una URL, aparece lista para
  guardar con dos botones, **Full** y **Summary**.
- Un atajo de teclado guarda directamente lo que haya en el portapapeles con el
  default configurado, sin abrir nada.
- El icono lleva un contador mientras hay links procesándose.
- El panel muestra los últimos guardados y los que fallaron, con un botón para
  reintentar, y un botón para abrir la biblioteca.
- El widget no sabe nada de HTML ni de IA: lanza `oknowledge add` y lee
  `~/.local/state/oknowledge/queue/`.

## La web

`oknowledge serve` levanta FastAPI en el puerto 8787 y abre el navegador. Se
apaga sola después de 15 minutos sin pedidos. Sin framework de frontend: HTML
servido con un poco de JavaScript.

| Pantalla | Qué tiene |
|---|---|
| **Library** | grilla de tarjetas con portada, título, categoría y tags; chips para filtrar por categoría y por tag; lo más nuevo primero |
| **Search** | campo siempre visible; busca en título, resumen, puntos, tags y en el contenido completo cuando está; cada resultado muestra el fragmento donde apareció |
| **Item** | resumen, puntos, contenido original si está; abrir el link, cambiar categoría, editar tags, reprocesar con otro motor, borrar |
| **Categories** | renombrar y fusionar, reescribiendo las notas afectadas y regenerando los índices |
| **Settings** | la cadena de motores (habilitar, deshabilitar, reordenar), el modelo de cada uno, el idioma y el default `full`/`summary` |

El índice se arma en memoria al arrancar leyendo el frontmatter de todas las
notas, y se refresca cuando cambia un archivo. Con unos cientos de notas es
instantáneo.

**La web nunca escribe Markdown por su cuenta:** toda modificación pasa por la
misma capa `vault.py` que usa el CLI.

### Criterio visual

Moderna y minimalista, sin ruido:

- Una sola columna de contenido, sin sidebar permanente.
- Tipografía grande y cómoda para los resúmenes: se diseñó para leer, no para
  administrar.
- Color sólo donde significa algo — la categoría —; el resto en escala de
  grises.
- Las acciones de una ficha aparecen al pasar el mouse, no antes.
- Modo claro y oscuro según el sistema.

## Configuración

`~/.config/oknowledge/config.toml`, permisos `600`:

```toml
vault = "/home/fer/Documents/obsidian_vaults/fer"
folder = "oknowledge"
default_content = "full"        # full | summary

[ai]
chain = ["opencode"]            # orden = prioridad; lo que no está, no se usa
language = "es"

[ai.opencode]
model = "opencode/ling-3.1-flash-free"

[ai.ollama]
model = "qwen2.5:7b"
url = "http://localhost:11434"

[ai.api]
provider = "anthropic"
model = "claude-sonnet-5"
key_env = "ANTHROPIC_API_KEY"

[web]
port = 8787
idle_timeout = 900
```

## Estados y errores

Cada link tiene un estado en la cola y en el frontmatter de su nota:

| Estado | Qué significa |
|---|---|
| `pending` | en proceso |
| `ok` | se extrajo y se analizó |
| `partial` | la nota existe, pero falta algo: no se pudo extraer el texto, o la IA no respondió. Tiene URL, fecha y lo que se haya averiguado |
| `failed` | ni siquiera se pudo resolver la URL |

`oknowledge retry` toma los `partial` y `failed` y los reintenta. El widget los
muestra con un botón de reintento. **En ningún caso se pierde la URL.**

## Pruebas

`pytest`, sin red en ningún test.

- **Extractores:** páginas reales bajadas una vez y guardadas como fixtures.
  Verifican que salga el texto del artículo y no el menú ni la publicidad.
- **IA:** el motor `fake` permite probar el pipeline entero. Aparte, tests de
  la validación con salidas rotas a propósito: JSON inválido, quince tags,
  categoría vacía, categoría que difiere de una existente sólo en acentos.
- **Vault:** se escribe en un vault temporal y se verifica el frontmatter, el
  nombre del archivo y el índice regenerado. **Un test comprueba que una nota
  sin el marcador `oknowledge` no se modifique ni se borre nunca.**
- **Idempotencia:** el mismo link dos veces no duplica.
- **Reindex:** borrar una nota a mano la saca del índice; cambiarle la
  categoría a mano la mueve de índice.
- **Web:** las rutas con el cliente de prueba de FastAPI sobre un vault de
  fixture.

## Verificación en vivo

1. `omarchy plugin validate` limpio y sin warnings QML en el log.
2. Pegar y revisar la nota resultante de: un artículo, un video de YouTube con
   transcripción, un PDF y un repositorio de GitHub.
3. Un link con la red cortada: la nota se crea `partial` y `retry` la completa.
4. Pegar el mismo link dos veces: no se duplica.
5. Cambiar `category` a mano en Obsidian y correr `reindex`: la nota cambia de
   índice.
6. Fusionar dos categorías desde la web y confirmar que las notas afectadas y
   los índices quedan consistentes.
7. Cambiar la cadena a `["ollama"]` y repetir el punto 2.

## Fuera de alcance

- **Preguntar en lenguaje natural** sobre la biblioteca. El diseño lo deja
  servido: el contenido está guardado y hay un servidor donde enchufarlo, pero
  embeddings y búsqueda semántica son un proyecto aparte.
- **Importar lo viejo**: favoritos del navegador, links de WhatsApp, archivos
  de texto. Merece un `oknowledge import`, después de que el flujo nuevo ande.
- Sincronizar entre máquinas, varios usuarios, publicar el plugin.
- Traducir la interfaz al español.
