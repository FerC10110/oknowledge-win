# oknowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pegar un link y que quede en el vault de Obsidian como una nota con resumen, categoría y tags, hojeable y buscable desde una web local.

**Architecture:** un paquete Python con tres capas sin dependencias circulares — extractores que convierten una URL en texto, motores de IA intercambiables que convierten texto en un `Analysis`, y `vault.py`, el único lugar del sistema que escribe Markdown. Encima, un CLI de cinco subcomandos, una web FastAPI que lee el vault, y un plugin de Omarchy que no hace más que invocar al CLI.

**Tech Stack:** Python 3.13, trafilatura, pypdf, httpx, FastAPI + uvicorn, Jinja2, PyYAML, pytest. `yt-dlp` como binario del sistema. QML/Quickshell para el plugin.

**Spec:** `/home/fer/Projects/oknowledge/docs/2026-10-03-oknowledge-design.md`

## Global Constraints

- El vault es la única fuente de verdad. No hay base de datos: todo índice se reconstruye leyendo Markdown.
- El sistema escribe **sólo** dentro de `<vault>/oknowledge/` y **sólo** en archivos cuyo frontmatter tenga `oknowledge: 1`. Un archivo sin ese marcador no se modifica ni se borra jamás.
- Nunca se pierde un link: si falla la extracción o la IA, la nota se crea igual con `status: partial`.
- Las claves del frontmatter, los nombres de archivo, el código y los textos de interfaz van en **inglés**. El contenido que genera la IA sale en el idioma de `[ai] language` (default `es`).
- El idioma de la interfaz es **inglés por defecto, español opcional**, leído de `~/.config/omarchy/plugin-language.json`. No entra en `config.toml`.
- Ningún test toca la red. Las páginas, los JSON de yt-dlp y de GitHub son fixtures en `tests/fixtures/`.
- Ningún extractor ejecuta JavaScript ni abre un navegador.
- `datetime.datetime.now(datetime.timezone.utc)`, nunca `utcnow()`.
- Los commits no llevan líneas de atribución a Claude.
- La web es una sola columna, sin sidebar permanente, color sólo en la categoría, acciones visibles al hover, modo claro y oscuro según el sistema.

## Review Focus

Cinco cosas que el spec implica, que van a pasar en la vida real, y que sin un test que las fije rompen el programa:

1. **Una URL con `utm_*`, fragmento y el host en mayúsculas** tiene que producir el mismo `id` que la versión limpia, o el mismo link se guarda dos veces. *(Task 2)*
2. **La IA devuelve el JSON envuelto en ` ```json ` o con una frase antes**, porque es lo que hacen los modelos chicos: hay que parsearlo igual en vez de tratarlo como fallo. *(Task 5)*
3. **Un título que no deja slug** — sólo emojis, sólo kanji, sólo signos — tiene que producir igual un nombre de archivo válido y único, no uno vacío que pise a otro. *(Task 3)*
4. **Una nota tuya, sin marcador, parada dentro de `oknowledge/links/`** no se puede tocar ni al reindexar ni al fusionar categorías. *(Task 3 y Task 13)*
5. **Una página que devuelve 404, o que no tiene texto extraíble**, tiene que terminar en una nota `partial` con la URL y la fecha, nunca en un link perdido. *(Task 10)*

---

## Estructura de archivos

```
src/oknowledge/
  __init__.py
  config.py        Config y su carga desde TOML
  i18n.py          idioma de interfaz: lee el archivo compartido de Omarchy
  urls.py          normalización de URL e id estable
  model.py         Note, Analysis, Extracted, QueueEntry
  vault.py         ÚNICA capa que escribe Markdown: notas e índices
  queue.py         estado por link y locks
  net.py           descarga HTTP (lo único que toca la red)
  extract/
    __init__.py    detect_type() y dispatch
    article.py     trafilatura
    youtube.py     yt-dlp
    github.py      API pública
    pdf.py         pypdf
    social.py      Reddit y mejor esfuerzo
  ai/
    __init__.py    la cadena con fallback
    base.py        Analysis, validación, normalización, render del prompt
    opencode.py
    ollama.py
    api.py
    fake.py        motor de tests
  prompts/analyze.txt
  pipeline.py      add(): orquesta todo lo anterior
  cli.py           add · serve · reindex · retry · status
  web/
    app.py         FastAPI y rutas
    index.py       índice en memoria del vault
    templates/     Jinja2
    static/        un CSS
plugin/            el plugin de Omarchy
tests/
  fixtures/
pyproject.toml
```

---

### Task 1: Esqueleto del paquete y configuración

**Files:**
- Create: `pyproject.toml`
- Create: `src/oknowledge/__init__.py`
- Create: `src/oknowledge/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada, es la primera tarea.
- Produces: `Config` (dataclass congelada con `vault: Path`, `folder: str`, `default_content: str`, `chain: tuple[str, ...]`, `language: str`, `engines: dict[str, dict]`, `port: int`, `idle_timeout: int`, y las propiedades `root`, `links_dir`, `attachments_dir`), `load(path: Path) -> Config`, `ConfigError`, `CONFIG_PATH`, `ENGINE_NAMES`.

- [ ] **Step 1: Crear el proyecto y el venv**

```bash
cd /home/fer/Projects/oknowledge
mkdir -p src/oknowledge tests/fixtures
touch src/oknowledge/__init__.py
python3 -m venv ~/.local/share/oknowledge/venv
~/.local/share/oknowledge/venv/bin/pip install -q --upgrade pip
```

`pyproject.toml`:

```toml
[project]
name = "oknowledge"
version = "0.1.0"
description = "Save a link, get a summarized note in your Obsidian vault"
requires-python = ">=3.13"
dependencies = [
  "trafilatura>=2.0",
  "pypdf>=5.1",
  "httpx>=0.28",
  "fastapi>=0.115",
  "uvicorn>=0.34",
  "jinja2>=3.1",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3"]

[project.scripts]
oknowledge = "oknowledge.cli:main"

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```bash
~/.local/share/oknowledge/venv/bin/pip install -q -e '.[dev]'
```

De acá en adelante, `pytest` significa `~/.local/share/oknowledge/venv/bin/pytest`.

- [ ] **Step 2: Escribir el test que falla**

`tests/test_config.py`:

```python
import pytest

from oknowledge.config import Config, ConfigError, load


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_reads_the_values(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f"""
vault = "{vault}"
default_content = "summary"

[ai]
chain = ["ollama", "opencode"]
language = "en"

[ai.ollama]
model = "qwen2.5:7b"

[web]
port = 9000
""")
    cfg = load(path)
    assert cfg.vault == vault
    assert cfg.default_content == "summary"
    assert cfg.chain == ("ollama", "opencode")
    assert cfg.language == "en"
    assert cfg.engines["ollama"]["model"] == "qwen2.5:7b"
    assert cfg.port == 9000


def test_what_the_file_omits_takes_the_default(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n'))
    assert cfg.folder == "oknowledge"
    assert cfg.default_content == "full"
    assert cfg.chain == ("opencode",)
    assert cfg.language == "es"
    assert cfg.port == 8787
    assert cfg.idle_timeout == 900


def test_the_paths_hang_off_the_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n'))
    assert cfg.root == vault / "oknowledge"
    assert cfg.links_dir == vault / "oknowledge" / "links"
    assert cfg.attachments_dir == vault / "oknowledge" / "attachments"


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(ConfigError, match="no config file"):
        load(tmp_path / "nope.toml")


def test_a_vault_that_does_not_exist_is_an_error(tmp_path):
    path = write_config(tmp_path, 'vault = "/no/such/vault"\n')
    with pytest.raises(ConfigError, match="vault"):
        load(path)


def test_an_unknown_engine_in_the_chain_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n\n[ai]\nchain = ["gpt5"]\n')
    with pytest.raises(ConfigError, match="gpt5"):
        load(path)


def test_an_empty_chain_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n\n[ai]\nchain = []\n')
    with pytest.raises(ConfigError, match="chain"):
        load(path)


def test_an_unknown_content_mode_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\ndefault_content = "half"\n')
    with pytest.raises(ConfigError, match="half"):
        load(path)
```

- [ ] **Step 3: Correrlo y ver que falla**

Run: `pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.config'`

- [ ] **Step 4: Escribir `config.py`**

```python
"""La configuración del usuario, con sus defaults y su validación.

El idioma de la interfaz no vive acá: es una preferencia del escritorio,
compartida con los demás plugins, y la lee i18n.py.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "oknowledge" / "config.toml"
ENGINE_NAMES = ("opencode", "ollama", "api", "fake")
CONTENT_MODES = ("full", "summary")


class ConfigError(Exception):
    """La configuración falta, o está y no se puede usar."""


@dataclass(frozen=True)
class Config:
    vault: Path
    folder: str = "oknowledge"
    default_content: str = "full"
    chain: tuple[str, ...] = ("opencode",)
    language: str = "es"
    engines: dict[str, dict] = field(default_factory=dict)
    port: int = 8787
    idle_timeout: int = 900

    @property
    def root(self) -> Path:
        return self.vault / self.folder

    @property
    def links_dir(self) -> Path:
        return self.root / "links"

    @property
    def attachments_dir(self) -> Path:
        return self.root / "attachments"


def load(path: Path = CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"no config file at {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    raw_vault = data.get("vault")
    if not raw_vault:
        raise ConfigError("vault is required in the config file")
    vault = Path(raw_vault).expanduser()
    if not vault.is_dir():
        raise ConfigError(f"vault is not a directory: {vault}")

    content = data.get("default_content", "full")
    if content not in CONTENT_MODES:
        raise ConfigError(f"default_content must be full or summary, not {content!r}")

    ai = data.get("ai", {})
    chain = tuple(ai.get("chain", ("opencode",)))
    if not chain:
        raise ConfigError("ai.chain cannot be empty: nothing would analyse the page")
    for name in chain:
        if name not in ENGINE_NAMES:
            raise ConfigError(f"unknown engine in ai.chain: {name!r}")

    engines = {name: dict(value) for name, value in ai.items() if isinstance(value, dict)}
    web = data.get("web", {})

    return Config(
        vault=vault,
        folder=data.get("folder", "oknowledge"),
        default_content=content,
        chain=chain,
        language=ai.get("language", "es"),
        engines=engines,
        port=int(web.get("port", 8787)),
        idle_timeout=int(web.get("idle_timeout", 900)),
    )
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_config.py -v`
Expected: PASS, 8 tests

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src tests .gitignore
git commit -m "feat: project skeleton and configuration"
```

---

### Task 2: URLs — normalización e id estable

**Files:**
- Create: `src/oknowledge/urls.py`
- Test: `tests/test_urls.py`

**Interfaces:**
- Consumes: nada.
- Produces: `normalize(url: str) -> str`, `link_id(url: str) -> str` (12 caracteres hex).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_urls.py`:

```python
from oknowledge.urls import link_id, normalize


def test_tracking_fragment_and_case_do_not_change_the_id():
    # El mismo artículo compartido por WhatsApp y copiado del navegador.
    dirty = "HTTPS://WWW.Example.com/Post/?utm_source=wa&utm_medium=x&id=7#intro"
    clean = "https://example.com/Post?id=7"
    assert normalize(dirty) == clean
    assert link_id(dirty) == link_id(clean)


def test_the_youtube_video_id_survives_but_the_share_token_does_not():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=AbC123"
    assert normalize(url) == "https://youtube.com/watch?v=dQw4w9WgXcQ"


def test_different_pages_get_different_ids():
    assert link_id("https://example.com/a") != link_id("https://example.com/b")


def test_the_order_of_the_query_does_not_matter():
    assert normalize("https://e.com/x?b=2&a=1") == normalize("https://e.com/x?a=1&b=2")


def test_the_id_is_twelve_hex_characters():
    value = link_id("https://example.com/")
    assert len(value) == 12
    assert all(c in "0123456789abcdef" for c in value)


def test_a_url_without_scheme_is_assumed_https():
    assert normalize("example.com/post") == "https://example.com/post"


def test_the_root_path_keeps_its_slash():
    assert normalize("https://example.com/") == "https://example.com/"
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_urls.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.urls'`

- [ ] **Step 3: Escribir `urls.py`**

```python
"""Normalizar una URL para que el mismo link no entre dos veces.

El id de un link es el hash de su forma normalizada. Dos URLs que llevan a
la misma página -- una copiada del navegador, otra reenviada por WhatsApp con
parámetros de seguimiento -- tienen que dar el mismo id.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_",)
TRACKING_EXACT = frozenset({
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "ref", "ref_src", "ref_url", "si", "spm", "_hsenc", "_hsmi",
})


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in TRACKING_EXACT or any(key.startswith(p) for p in TRACKING_PREFIXES)


def normalize(url: str) -> str:
    raw = url.strip()
    if "//" not in raw.split("?", 1)[0][:8]:
        raw = "https://" + raw
    parts = urlsplit(raw)

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(k)
    )

    return urlunsplit((parts.scheme.lower() or "https", netloc, path, urlencode(query), ""))


def link_id(url: str) -> str:
    return hashlib.sha256(normalize(url).encode("utf-8")).hexdigest()[:12]
```

- [ ] **Step 4: Correr los tests**

Run: `pytest tests/test_urls.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/oknowledge/urls.py tests/test_urls.py
git commit -m "feat: url normalization and stable link ids"
```

---

### Task 3: El vault — escribir y leer una nota, y el marcador que protege las tuyas

Esta es la tarea más delicada del plan: `vault.py` es el único módulo del sistema que escribe Markdown, y el único que puede romper notas del usuario.

**Files:**
- Create: `src/oknowledge/model.py`
- Create: `src/oknowledge/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Consumes: `Config` de Task 1.
- Produces: `Note` (dataclass), `slug(text: str, fallback: str) -> str`, `render(note: Note, language: str) -> str`, `note_path(cfg, note) -> Path`, `write_note(cfg, note, language) -> Path`, `read_front(path) -> dict | None`, `read_note(path) -> Note | None`, `ProtectedNote`, `MARKER`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_vault.py`:

```python
import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    ProtectedNote, note_path, read_front, read_note, slug, write_note,
)


def make_config(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def make_note(**over):
    values = dict(
        id="9f2a1c4b8e07",
        url="https://arstechnica.com/vpn",
        title="WireGuard vs OpenVPN",
        category="Redes",
        tags=["vpn", "wireguard"],
        type="article",
        source="arstechnica.com",
        saved="2026-10-03",
        summary="Compara ambos protocolos.\nY explica cuál conviene.",
        points=["Corre en el kernel", "Menos código que auditar"],
    )
    values.update(over)
    return Note(**values)


def test_a_note_survives_the_round_trip(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(body="El texto entero del artículo.", author="Dan Goodin")
    path = write_note(cfg, note, "es")

    assert path.name == "2026-10-03-wireguard-vs-openvpn.md"
    back = read_note(path)
    assert back == note


def test_the_frontmatter_carries_the_marker(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(), "es")
    front = read_front(path)
    assert front["oknowledge"] == 1
    assert front["id"] == "9f2a1c4b8e07"
    assert front["category"] == "Redes"


def test_summary_mode_leaves_no_original_content(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(content="summary", body=None), "es")
    text = path.read_text(encoding="utf-8")
    assert "Contenido original" not in text
    assert read_note(path).body is None


def test_a_title_with_no_latin_letters_still_makes_a_filename(tmp_path):
    # Un título de puros emojis o de kanji no deja slug: cae al id, que es
    # siempre válido y siempre único.
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(title="🔥🔥🔥"), "es")
    assert path.name == "2026-10-03-9f2a1c4b8e07.md"
    assert read_note(path).title == "🔥🔥🔥"


def test_slug_falls_back_only_when_there_is_nothing_to_use():
    assert slug("Qué pasó en Córdoba", "x") == "que-paso-en-cordoba"
    assert slug("   ", "fallback") == "fallback"
    assert slug("***", "fallback") == "fallback"


def test_a_note_of_yours_in_our_folder_is_never_touched(tmp_path):
    # Una nota tuya, sin marcador, parada justo donde iría la nuestra.
    cfg = make_config(tmp_path)
    mine = cfg.links_dir / "2026-10-03-wireguard-vs-openvpn.md"
    mine.write_text("# Mis apuntes\n\nNo me toques.\n", encoding="utf-8")
    before = mine.read_text(encoding="utf-8")

    path = write_note(cfg, make_note(), "es")

    assert path.name == "2026-10-03-wireguard-vs-openvpn-2.md"
    assert mine.read_text(encoding="utf-8") == before


def test_a_file_without_the_marker_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    other = cfg.links_dir / "ajena.md"
    other.write_text("---\ntitle: mía\n---\n\nhola\n", encoding="utf-8")
    assert read_front(other) is None
    assert read_note(other) is None


def test_rewriting_the_same_link_reuses_its_file(tmp_path):
    cfg = make_config(tmp_path)
    first = write_note(cfg, make_note(), "es")
    second = write_note(cfg, make_note(summary="Otro resumen."), "es")
    assert first == second
    assert read_note(second).summary == "Otro resumen."
    assert len(list(cfg.links_dir.glob("*.md"))) == 1


def test_a_foreign_file_on_the_final_path_is_refused(tmp_path):
    # Defensa en profundidad: note_path ya esquiva los archivos ajenos, así
    # que llegar acá significa que algo cambió abajo nuestro.
    cfg = make_config(tmp_path)
    note = make_note()
    target = note_path(cfg, note)
    target.write_text("no soy tuya\n", encoding="utf-8")
    with pytest.raises(ProtectedNote):
        write_note(cfg, note, "es", path=target)
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_vault.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.model'`

- [ ] **Step 3: Escribir `model.py`**

```python
"""Las formas que viajan entre las capas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    """Un link guardado, tal como queda en el vault."""

    id: str
    url: str
    title: str
    category: str
    tags: list[str]
    type: str
    source: str
    saved: str                       # YYYY-MM-DD
    summary: str
    points: list[str] = field(default_factory=list)
    status: str = "ok"               # ok | partial | failed
    content: str = "full"            # full | summary
    author: str | None = None
    published: str | None = None     # YYYY-MM-DD
    cover: str | None = None         # ruta relativa a la nota
    body: str | None = None          # el texto extraído, si content == "full"
```

- [ ] **Step 4: Escribir `vault.py`**

```python
"""El único módulo que escribe Markdown.

Dos reglas, y las dos están acá por una razón: el vault es del usuario.

1. Sólo se escribe dentro de <vault>/<folder>/.
2. Sólo se tocan archivos cuyo frontmatter tenga `oknowledge: 1`. Un archivo
   sin ese marcador no se modifica ni se borra, aunque esté en nuestra carpeta
   y aunque se llame exactamente como el que íbamos a escribir.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

from .config import Config
from .model import Note

MARKER = "oknowledge"
MARKER_VERSION = 1

HEADINGS = {
    "es": ("Puntos clave", "Contenido original"),
    "en": ("Key points", "Original content"),
}

FRONTMATTER_ORDER = (
    "url", "title", "category", "tags", "type", "source", "author",
    "published", "saved", "cover", "content", "status", "id", MARKER,
)


class ProtectedNote(Exception):
    """El archivo de destino existe y no lleva nuestro marcador."""


def slug(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = plain.encode("ascii", "ignore").decode("ascii").lower()
    plain = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:60].strip("-")
    return plain or fallback


def render(note: Note, language: str) -> str:
    points_heading, content_heading = HEADINGS.get(language, HEADINGS["en"])

    front = {
        "url": note.url,
        "title": note.title,
        "category": note.category,
        "tags": list(note.tags),
        "type": note.type,
        "source": note.source,
        "author": note.author,
        "published": note.published,
        "saved": note.saved,
        "cover": note.cover,
        "content": note.content,
        "status": note.status,
        "id": note.id,
        MARKER: MARKER_VERSION,
    }
    front = {k: front[k] for k in FRONTMATTER_ORDER if front.get(k) is not None}
    head = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    parts = [f"---\n{head}\n---\n", f"# {note.title}\n", f"{note.summary.strip()}\n"]
    if note.points:
        bullets = "\n".join(f"- {p}" for p in note.points)
        parts.append(f"## {points_heading}\n\n{bullets}\n")
    if note.content == "full" and note.body:
        parts.append(f"## {content_heading}\n\n{note.body.strip()}\n")
    return "\n".join(parts)


def read_front(path: Path) -> dict | None:
    """El frontmatter, sólo si el archivo es nuestro. Si no, None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        front = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    if not isinstance(front, dict) or front.get(MARKER) != MARKER_VERSION:
        return None
    return front


def _split_body(text: str) -> tuple[str, list[str], str | None]:
    """Devuelve (resumen, puntos, contenido original) del cuerpo escrito por render()."""
    body = text.split("\n---", 1)[1]          # todo lo que viene después del frontmatter
    lines = body.splitlines()
    # Saltar hasta después del H1.
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    sections: list[list[str]] = [[]]
    for line in lines[start:]:
        if line.startswith("## "):
            sections.append([])
        else:
            sections[-1].append(line)
    summary = "\n".join(sections[0]).strip()
    points = [line[2:].strip() for line in sections[1] if line.startswith("- ")] if len(sections) > 1 else []
    original = "\n".join(sections[2]).strip() if len(sections) > 2 else None
    return summary, points, original or None


def read_note(path: Path) -> Note | None:
    front = read_front(path)
    if front is None or front.get("kind") == "index":
        return None
    summary, points, body = _split_body(path.read_text(encoding="utf-8"))
    return Note(
        id=front["id"],
        url=front["url"],
        title=front["title"],
        category=front["category"],
        tags=list(front.get("tags") or []),
        type=front["type"],
        source=front["source"],
        saved=str(front["saved"]),
        summary=summary,
        points=points,
        status=front.get("status", "ok"),
        content=front.get("content", "full"),
        author=front.get("author"),
        published=str(front["published"]) if front.get("published") else None,
        cover=front.get("cover"),
        body=body,
    )


def note_path(cfg: Config, note: Note) -> Path:
    stem = f"{note.saved}-{slug(note.title, note.id)}"
    candidate = cfg.links_dir / f"{stem}.md"
    n = 2
    while candidate.exists():
        existing = read_note(candidate)
        if existing is not None and existing.id == note.id:
            return candidate
        candidate = cfg.links_dir / f"{stem}-{n}.md"
        n += 1
    return candidate


def write_note(cfg: Config, note: Note, language: str, path: Path | None = None) -> Path:
    cfg.links_dir.mkdir(parents=True, exist_ok=True)
    target = path or note_path(cfg, note)
    if target.exists() and read_front(target) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    target.write_text(render(note, language), encoding="utf-8")
    return target
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_vault.py -v`
Expected: PASS, 9 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/model.py src/oknowledge/vault.py tests/test_vault.py
git commit -m "feat: write and read notes, and never touch a file without the marker"
```

---

### Task 4: Índices por categoría y `reindex`

**Files:**
- Modify: `src/oknowledge/vault.py`
- Test: `tests/test_indexes.py`

**Interfaces:**
- Consumes: `Note`, `read_note`, `read_front`, `write_note`, `MARKER` de Task 3.
- Produces: `all_notes(cfg) -> list[Note]`, `find_note(cfg, link_id) -> tuple[Path, Note] | None`, `index_path(cfg, category) -> Path`, `write_index(cfg, category, notes) -> Path`, `rebuild_indexes(cfg) -> list[Path]`, `categories(cfg) -> dict[str, int]`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_indexes.py`:

```python
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    all_notes, categories, find_note, index_path, rebuild_indexes, write_note,
)


def make_config(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def note(id, title, category, tags=("x",), saved="2026-10-03"):
    return Note(
        id=id, url=f"https://e.com/{id}", title=title, category=category,
        tags=list(tags), type="article", source="e.com", saved=saved,
        summary=f"Resumen de {title}.", points=["uno"],
    )


def test_an_index_lists_its_notes_newest_first(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Túneles SSH", "Redes", saved="2026-09-28"), "es")
    write_note(cfg, note("b2", "WireGuard", "Redes", saved="2026-10-03"), "es")

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert "# Redes · 2 links" in text
    assert text.index("WireGuard") < text.index("Túneles SSH")
    assert "[[2026-10-03-wireguard|WireGuard]]" in text
    assert "Generado por oknowledge" in text


def test_each_category_gets_its_own_index(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")

    rebuild_indexes(cfg)

    assert index_path(cfg, "Redes").exists()
    assert index_path(cfg, "Cocina").exists()


def test_an_index_left_without_notes_is_deleted(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    rebuild_indexes(cfg)
    assert index_path(cfg, "Redes").exists()

    path.unlink()
    rebuild_indexes(cfg)
    assert not index_path(cfg, "Redes").exists()


def test_changing_the_category_by_hand_moves_the_note(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    rebuild_indexes(cfg)

    path.write_text(path.read_text(encoding="utf-8").replace("category: Redes",
                                                             "category: Seguridad"), encoding="utf-8")
    rebuild_indexes(cfg)

    assert not index_path(cfg, "Redes").exists()
    assert "WireGuard" in index_path(cfg, "Seguridad").read_text(encoding="utf-8")


def test_a_file_of_yours_in_the_folder_is_not_an_index_and_is_not_deleted(tmp_path):
    cfg = make_config(tmp_path)
    mine = cfg.root / "Mis lecturas.md"
    mine.write_text("# Mis lecturas\n\nA mano.\n", encoding="utf-8")
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")

    rebuild_indexes(cfg)

    assert mine.read_text(encoding="utf-8") == "# Mis lecturas\n\nA mano.\n"


def test_a_category_with_a_slash_does_not_escape_the_folder(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Algo", "IA/LLMs"), "es")
    rebuild_indexes(cfg)
    created = index_path(cfg, "IA/LLMs")
    assert created.parent == cfg.root
    assert created.exists()


def test_find_note_locates_a_link_by_id(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    found = find_note(cfg, "a1")
    assert found is not None and found[1].title == "WireGuard"
    assert find_note(cfg, "zz") is None


def test_categories_counts_what_exists(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "SSH", "Redes"), "es")
    write_note(cfg, note("c3", "Masa madre", "Cocina"), "es")
    assert categories(cfg) == {"Cocina": 1, "Redes": 2}


def test_all_notes_ignores_files_that_are_not_ours(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    (cfg.links_dir / "ajena.md").write_text("# mía\n", encoding="utf-8")
    assert [n.id for n in all_notes(cfg)] == ["a1"]
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_indexes.py -v`
Expected: FAIL con `ImportError: cannot import name 'all_notes'`

- [ ] **Step 3: Agregar a `vault.py`**

```python
INDEX_NOTICE = "<!-- Generado por oknowledge. Los cambios a mano se pierden. -->"


def all_notes(cfg: Config) -> list[Note]:
    if not cfg.links_dir.is_dir():
        return []
    notes = [read_note(p) for p in sorted(cfg.links_dir.glob("*.md"))]
    return [n for n in notes if n is not None]


def find_note(cfg: Config, link_id: str) -> tuple[Path, Note] | None:
    if not cfg.links_dir.is_dir():
        return None
    for path in sorted(cfg.links_dir.glob("*.md")):
        note = read_note(path)
        if note is not None and note.id == link_id:
            return path, note
    return None


def categories(cfg: Config) -> dict[str, int]:
    counts: dict[str, int] = {}
    for note in all_notes(cfg):
        counts[note.category] = counts.get(note.category, 0) + 1
    return dict(sorted(counts.items()))


def index_path(cfg: Config, category: str) -> Path:
    # El nombre de la categoría lo escribe un modelo: nunca puede salir de
    # nuestra carpeta ni inventar subdirectorios.
    name = re.sub(r"[\\/:*?\"<>|]+", "-", category).strip(" .") or "Sin categoria"
    return cfg.root / f"{name}.md"


def write_index(cfg: Config, category: str, notes: list[Note]) -> Path:
    cfg.root.mkdir(parents=True, exist_ok=True)
    ordered = sorted(notes, key=lambda n: (n.saved, n.title), reverse=True)

    front = yaml.safe_dump(
        {MARKER: MARKER_VERSION, "kind": "index", "category": category},
        sort_keys=False, allow_unicode=True,
    ).strip()

    lines = [f"---\n{front}\n---\n", f"# {category} · {len(ordered)} links\n", f"{INDEX_NOTICE}\n"]
    for note in ordered:
        stem = note_path(cfg, note).stem
        tags = " ".join(f"#{t}" for t in note.tags)
        head = note.summary.strip().splitlines()[0] if note.summary.strip() else ""
        lines.append(f"- [[{stem}|{note.title}]]\n  `{tags}` — {head}")

    target = index_path(cfg, category)
    if target.exists() and read_front(target) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def rebuild_indexes(cfg: Config) -> list[Path]:
    grouped: dict[str, list[Note]] = {}
    for note in all_notes(cfg):
        grouped.setdefault(note.category, []).append(note)

    written = [write_index(cfg, category, notes) for category, notes in sorted(grouped.items())]

    keep = {p.name for p in written}
    for path in cfg.root.glob("*.md"):
        front = read_front(path)
        if front is not None and front.get("kind") == "index" and path.name not in keep:
            path.unlink()
    return written
```

- [ ] **Step 4: Correr los tests**

Run: `pytest tests/test_indexes.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Correr todo**

Run: `pytest -v`
Expected: PASS, 24 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/vault.py tests/test_indexes.py
git commit -m "feat: category indexes and reindex"
```

---

### Task 5: El análisis — prompt, validación y motor de prueba

**Files:**
- Create: `src/oknowledge/ai/__init__.py` (vacío por ahora)
- Create: `src/oknowledge/ai/base.py`
- Create: `src/oknowledge/ai/fake.py`
- Create: `src/oknowledge/prompts/analyze.txt`
- Modify: `pyproject.toml` (incluir los datos del paquete)
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `Analysis` (dataclass con `title`, `summary`, `points`, `category`, `tags`), `EngineError`, `AnalysisError`, `Engine` (protocolo con `name: str` y `complete(prompt: str) -> str`), `render_prompt(text, meta, known, language) -> str`, `extract_json(raw: str) -> dict`, `normalize_tags(tags) -> list[str]`, `canonical_category(category, known) -> str`, `analyze(engine, text, meta, known, language) -> Analysis`, `FakeEngine`.

- [ ] **Step 1: Escribir el prompt**

`src/oknowledge/prompts/analyze.txt`:

```text
Sos un bibliotecario. Analizás una página web y devolvés su ficha.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma:

{
  "title": "el título real de la página, limpio, sin el nombre del sitio",
  "summary": "de 5 a 10 líneas que cuenten lo que dice la página, no lo que es",
  "points": ["3 a 6 ideas concretas, una por línea"],
  "category": "una sola categoría",
  "tags": ["3 a 8 etiquetas, en minúsculas, una o dos palabras cada una"]
}

El resumen, los puntos, la categoría y las etiquetas van escritos en {{LANGUAGE}},
aunque la página esté en otro idioma.

El resumen cuenta el contenido: qué afirma, qué compara, a qué conclusión llega.
No escribas "este artículo trata sobre"; escribí directamente lo que dice.

Para la categoría, estas ya existen en la biblioteca:

{{CATEGORIES}}

Usá una de esas si alguna encaja razonablemente. Inventá una nueva sólo si
ninguna sirve, y que sea corta y general, del estilo de las existentes.

URL: {{URL}}
Título detectado: {{TITLE}}

Contenido:

{{TEXT}}
```

Agregar a `pyproject.toml`:

```toml
[tool.setuptools.package-data]
oknowledge = ["prompts/*.txt", "web/templates/*.html", "web/static/*"]
```

- [ ] **Step 2: Escribir el test que falla**

`tests/test_analysis.py`:

```python
import json

import pytest

from oknowledge.ai.base import (
    AnalysisError, Analysis, analyze, canonical_category, extract_json,
    normalize_tags, render_prompt,
)
from oknowledge.ai.fake import FakeEngine

GOOD = {
    "title": "WireGuard vs OpenVPN",
    "summary": "Compara ambos protocolos.",
    "points": ["Corre en el kernel", "Menos código"],
    "category": "redes",
    "tags": ["VPN", "WireGuard ", "Programación", "vpn"],
}
META = {"url": "https://e.com/vpn", "title": "WireGuard vs OpenVPN | Ars"}


def test_a_model_that_wraps_the_json_in_a_fence_is_understood():
    # Es lo que hacen los modelos chicos, y no es un error.
    raw = 'Claro, acá va:\n\n```json\n{"a": 1, "b": [2, 3]}\n```\n¡Listo!'
    assert extract_json(raw) == {"a": 1, "b": [2, 3]}


def test_plain_json_with_a_banner_before_it_is_understood():
    # opencode imprime una línea de encabezado antes de la respuesta.
    raw = '\n> build · ling-3.1-flash-free\n\n{"a": 1}\n'
    assert extract_json(raw) == {"a": 1}


def test_something_that_is_not_json_at_all_raises():
    with pytest.raises(AnalysisError):
        extract_json("no tengo idea de qué me pedís")


def test_tags_are_lowercased_deaccented_dashed_and_deduped():
    assert normalize_tags(GOOD["tags"]) == ["vpn", "wireguard", "programacion"]


def test_tags_are_capped_at_eight():
    assert len(normalize_tags([f"tag{i}" for i in range(20)])) == 8


def test_tags_that_normalize_to_nothing_are_dropped():
    assert normalize_tags(["", "   ", "***", "ok"]) == ["ok"]


def test_a_category_that_already_exists_keeps_its_spelling():
    assert canonical_category("redes", ["Redes", "Cocina"]) == "Redes"
    assert canonical_category("PROGRAMACION", ["Programación"]) == "Programación"


def test_a_genuinely_new_category_is_kept_as_is():
    assert canonical_category("Fotografía", ["Redes"]) == "Fotografía"


def test_the_prompt_carries_the_language_and_the_known_categories():
    prompt = render_prompt("el texto", META, ["Redes", "Cocina"], "es")
    assert "español" in prompt
    assert "Redes" in prompt and "Cocina" in prompt
    assert "https://e.com/vpn" in prompt
    assert "el texto" in prompt
    assert "{{" not in prompt


def test_analyze_returns_a_clean_analysis():
    engine = FakeEngine([json.dumps(GOOD)])
    result = analyze(engine, "texto", META, ["Redes"], "es")
    assert result == Analysis(
        title="WireGuard vs OpenVPN",
        summary="Compara ambos protocolos.",
        points=["Corre en el kernel", "Menos código"],
        category="Redes",
        tags=["vpn", "wireguard", "programacion"],
    )


def test_a_broken_answer_is_retried_once_with_a_stricter_prompt():
    engine = FakeEngine(["perdón, no entendí", json.dumps(GOOD)])
    result = analyze(engine, "texto", META, [], "es")
    assert result.title == "WireGuard vs OpenVPN"
    assert len(engine.prompts) == 2
    assert "ONLY" in engine.prompts[1] or "sólo" in engine.prompts[1].lower()


def test_two_broken_answers_in_a_row_raise():
    engine = FakeEngine(["no", "tampoco"])
    with pytest.raises(AnalysisError):
        analyze(engine, "texto", META, [], "es")


def test_an_answer_missing_a_required_field_raises():
    engine = FakeEngine([json.dumps({"title": "x"}), json.dumps({"title": "x"})])
    with pytest.raises(AnalysisError):
        analyze(engine, "texto", META, [], "es")


def test_an_empty_category_falls_back_instead_of_breaking():
    data = dict(GOOD, category="   ")
    engine = FakeEngine([json.dumps(data)])
    assert analyze(engine, "texto", META, [], "es").category == "Sin clasificar"


def test_text_longer_than_the_limit_is_cut_from_the_end():
    prompt = render_prompt("x" * 100_000, META, [], "es", limit=1000)
    assert prompt.count("x") == 1000
```

- [ ] **Step 3: Correrlo y ver que falla**

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.ai'`

- [ ] **Step 4: Escribir `ai/base.py` y `ai/fake.py`**

`src/oknowledge/ai/base.py`:

```python
"""Lo que el sistema le pide a un modelo, y cómo desconfía de la respuesta.

Un motor sabe una sola cosa: recibir un prompt y devolver texto. Todo lo
demás -- armar el pedido, encontrar el JSON entre el ruido, validarlo y
normalizarlo -- vive acá, igual para los tres motores.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

DEFAULT_LIMIT = 24_000
UNCATEGORIZED = "Sin clasificar"
LANGUAGE_NAMES = {"es": "español", "en": "inglés"}
STRICTER = (
    "\n\nTu respuesta anterior no era JSON válido. Respondé ONLY con el objeto "
    "JSON pedido: sin explicación, sin comentarios, sin ```."
)
REQUIRED = ("title", "summary", "points", "category", "tags")


class EngineError(Exception):
    """El motor no pudo responder: no está, falló, se quedó sin cuota."""


class AnalysisError(Exception):
    """El motor respondió, pero la respuesta no sirve."""


class Engine(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


@dataclass
class Analysis:
    title: str
    summary: str
    points: list[str]
    category: str
    tags: list[str]


def _deaccent(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_tags(tags) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        clean = re.sub(r"[^a-z0-9]+", "-", _deaccent(str(tag)).lower()).strip("-")
        if clean and clean not in out:
            out.append(clean)
    return out[:8]


def canonical_category(category: str, known) -> str:
    wanted = _deaccent(str(category or "")).strip().lower()
    if not wanted:
        return UNCATEGORIZED
    for existing in known or []:
        if _deaccent(existing).strip().lower() == wanted:
            return existing
    return str(category).strip()


def render_prompt(text: str, meta: dict, known, language: str, limit: int = DEFAULT_LIMIT) -> str:
    template = files("oknowledge").joinpath("prompts/analyze.txt").read_text(encoding="utf-8")
    listed = "\n".join(f"- {c}" for c in (known or [])) or "- (todavía no hay ninguna)"
    body = text[:limit]
    return (
        template
        .replace("{{LANGUAGE}}", LANGUAGE_NAMES.get(language, language))
        .replace("{{CATEGORIES}}", listed)
        .replace("{{URL}}", meta.get("url", ""))
        .replace("{{TITLE}}", meta.get("title") or "")
        .replace("{{TEXT}}", body)
    )


def extract_json(raw: str) -> dict:
    """El primer objeto JSON del texto, venga como venga."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AnalysisError("the answer had no JSON object in it")


def _to_analysis(data: dict, known) -> Analysis:
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise AnalysisError(f"the answer is missing: {', '.join(missing)}")
    summary = str(data["summary"]).strip()
    if not summary:
        raise AnalysisError("the answer has an empty summary")
    points = [str(p).strip() for p in (data["points"] or []) if str(p).strip()]
    return Analysis(
        title=str(data["title"]).strip(),
        summary=summary,
        points=points[:6],
        category=canonical_category(data["category"], known),
        tags=normalize_tags(data["tags"]),
    )


def analyze(engine: Engine, text: str, meta: dict, known, language: str) -> Analysis:
    prompt = render_prompt(text, meta, known, language)
    for attempt in (prompt, prompt + STRICTER):
        try:
            return _to_analysis(extract_json(engine.complete(attempt)), known)
        except AnalysisError as error:
            last = error
    raise AnalysisError(f"the engine never produced a usable answer: {last}")
```

`src/oknowledge/ai/fake.py`:

```python
"""Un motor que devuelve lo que le digas. Sólo para los tests."""

from __future__ import annotations

from .base import EngineError


class FakeEngine:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            raise EngineError("the fake engine ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_analysis.py -v`
Expected: PASS, 15 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/ai src/oknowledge/prompts pyproject.toml tests/test_analysis.py
git commit -m "feat: prompt, answer validation and a fake engine for tests"
```

---

### Task 6: Los tres motores y la cadena con respaldo

**Files:**
- Create: `src/oknowledge/ai/opencode.py`
- Create: `src/oknowledge/ai/ollama.py`
- Create: `src/oknowledge/ai/api.py`
- Modify: `src/oknowledge/ai/__init__.py`
- Test: `tests/test_engines.py`

**Interfaces:**
- Consumes: `Engine`, `EngineError`, `Analysis`, `analyze` de Task 5; `Config` de Task 1.
- Produces: `OpenCodeEngine`, `OllamaEngine`, `ApiEngine`, `build_engine(name, cfg) -> Engine`, `analyze_with_chain(cfg, text, meta, known, engine=None) -> tuple[Analysis, str]`, `AllEnginesFailed`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_engines.py`:

```python
import json

import pytest

from oknowledge.ai import AllEnginesFailed, analyze_with_chain, build_engine
from oknowledge.ai.api import ApiEngine
from oknowledge.ai.base import EngineError
from oknowledge.ai.ollama import OllamaEngine
from oknowledge.ai.opencode import OpenCodeEngine
from oknowledge.config import Config

GOOD = json.dumps({
    "title": "T", "summary": "S", "points": ["p"], "category": "Redes", "tags": ["vpn"],
})
META = {"url": "https://e.com/x", "title": "T"}


def make_config(tmp_path, chain):
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    return Config(vault=vault, chain=tuple(chain), engines={"fake": {}})


def test_opencode_runs_in_an_empty_directory_and_without_plugins(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        return type("P", (), {"returncode": 0, "stdout": GOOD, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    out = OpenCodeEngine(model="opencode/x-free").complete("hola")

    assert out == GOOD
    assert seen["argv"][:5] == ["opencode", "run", "--pure", "-m", "opencode/x-free"]
    assert seen["argv"][5] == "hola"
    assert not list(__import__("pathlib").Path(seen["cwd"]).iterdir())


def test_opencode_failing_is_an_engine_error(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda argv, **kw: type("P", (), {"returncode": 1, "stdout": "", "stderr": "nope"})(),
    )
    with pytest.raises(EngineError, match="nope"):
        OpenCodeEngine(model="m").complete("hola")


def test_ollama_asks_for_json_and_reads_the_message(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return {"message": {"content": GOOD}}

        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    out = OllamaEngine(model="qwen2.5:7b", url="http://localhost:11434",
                       ensure=lambda: None).complete("hola")

    assert out == GOOD
    assert seen["url"] == "http://localhost:11434/api/chat"
    assert seen["body"]["format"] == "json"
    assert seen["body"]["stream"] is False
    assert seen["body"]["messages"][0]["content"] == "hola"


def test_the_api_engine_sends_the_key_from_the_environment(monkeypatch):
    seen = {}

    class Response:
        def json(self):
            return {"content": [{"text": GOOD}]}

        def raise_for_status(self):
            pass

    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr("httpx.post", lambda url, headers=None, json=None, timeout=None:
                        seen.update(url=url, headers=headers, body=json) or Response())

    out = ApiEngine(provider="anthropic", model="claude-sonnet-5", key_env="MY_KEY").complete("hola")

    assert out == GOOD
    assert seen["headers"]["x-api-key"] == "sk-secret"
    assert "anthropic" in seen["url"]


def test_the_api_engine_without_a_key_says_so(monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    with pytest.raises(EngineError, match="MY_KEY"):
        ApiEngine(provider="anthropic", model="m", key_env="MY_KEY").complete("hola")


def test_the_chain_falls_through_to_the_next_engine(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    broken = FakeEngine([EngineError("sin cuota")])
    working = FakeEngine([GOOD])
    engines = {"opencode": broken, "ollama": working}
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])

    cfg = make_config(tmp_path, ["opencode", "ollama"])
    analysis, used = analyze_with_chain(cfg, "texto", META, [])

    assert used == "ollama"
    assert analysis.category == "Redes"


def test_when_every_engine_fails_the_error_names_them_all(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: FakeEngine([EngineError(f"{name} caído")]),
    )
    cfg = make_config(tmp_path, ["opencode", "ollama"])
    with pytest.raises(AllEnginesFailed) as error:
        analyze_with_chain(cfg, "texto", META, [])
    assert "opencode" in str(error.value) and "ollama" in str(error.value)


def test_forcing_an_engine_ignores_the_chain(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    calls = []
    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: calls.append(name) or FakeEngine([GOOD]),
    )
    cfg = make_config(tmp_path, ["opencode", "ollama"])
    analyze_with_chain(cfg, "texto", META, [], engine="ollama")
    assert calls == ["ollama"]


def test_build_engine_refuses_a_name_it_does_not_know(tmp_path):
    with pytest.raises(EngineError, match="gpt5"):
        build_engine("gpt5", make_config(tmp_path, ["opencode"]))
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_engines.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.ai.opencode'`

- [ ] **Step 3: Escribir los tres motores**

`src/oknowledge/ai/opencode.py`:

```python
"""opencode, el motor que no necesita ninguna credencial.

Se lo corre en un directorio temporal vacío y con --pure: es un agente, no un
servicio de texto, así que se le quita todo lo que podría tentarlo a tocar
archivos.
"""

from __future__ import annotations

import subprocess
import tempfile

from .base import EngineError


class OpenCodeEngine:
    name = "opencode"

    def __init__(self, model: str, binary: str = "opencode", timeout: int = 300):
        self.model = model
        self.binary = binary
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        argv = [self.binary, "run", "--pure", "-m", self.model, prompt]
        try:
            with tempfile.TemporaryDirectory() as cwd:
                proc = subprocess.run(
                    argv, cwd=cwd, capture_output=True, text=True, timeout=self.timeout,
                )
        except FileNotFoundError as error:
            raise EngineError(f"opencode is not installed: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise EngineError(f"opencode timed out after {self.timeout}s") from error
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        return proc.stdout
```

`src/oknowledge/ai/ollama.py`:

```python
"""ollama: el único motor donde el texto no sale de la máquina."""

from __future__ import annotations

import shutil
import subprocess
import time

import httpx

from .base import EngineError


def ensure_running(url: str, timeout: float = 15.0) -> None:
    """Si ollama está instalado pero apagado, lo levanta en vez de fallar."""
    try:
        httpx.get(f"{url}/api/tags", timeout=2.0).raise_for_status()
        return
    except Exception:
        pass
    if not shutil.which("ollama"):
        raise EngineError("ollama is not installed")
    subprocess.Popen(
        ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{url}/api/tags", timeout=2.0).raise_for_status()
            return
        except Exception:
            time.sleep(0.5)
    raise EngineError("ollama did not come up")


class OllamaEngine:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434",
                 timeout: int = 300, ensure=None):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._ensure = ensure if ensure is not None else lambda: ensure_running(self.url)

    def complete(self, prompt: str) -> str:
        self._ensure()
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }
        try:
            response = httpx.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except EngineError:
            raise
        except Exception as error:
            raise EngineError(f"ollama failed: {error}") from error
```

`src/oknowledge/ai/api.py`:

```python
"""El motor con API key. Preparado aunque no esté en la cadena.

La key no se guarda nunca en el vault ni en el repo: sale de una variable de
entorno, o del config.toml que vive con permisos 600.
"""

from __future__ import annotations

import os

import httpx

from .base import EngineError

ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}


class ApiEngine:
    name = "api"

    def __init__(self, provider: str, model: str, key_env: str = "",
                 key: str = "", base_url: str = "", timeout: int = 300,
                 max_tokens: int = 2000):
        if provider not in ENDPOINTS:
            raise EngineError(f"unknown provider: {provider!r}")
        self.provider = provider
        self.model = model
        self.key_env = key_env
        self.key = key
        self.url = base_url or ENDPOINTS[provider]
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _secret(self) -> str:
        secret = self.key or (os.environ.get(self.key_env, "") if self.key_env else "")
        if not secret:
            raise EngineError(f"no API key: set {self.key_env or 'ai.api.key'}")
        return secret

    def complete(self, prompt: str) -> str:
        secret = self._secret()
        messages = [{"role": "user", "content": prompt}]
        if self.provider == "anthropic":
            headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
            body = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages}
        else:
            headers = {"Authorization": f"Bearer {secret}"}
            body = {"model": self.model, "messages": messages}
        try:
            response = httpx.post(self.url, headers=headers, json=body, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as error:
            raise EngineError(f"{self.provider} failed: {error}") from error
        if self.provider == "anthropic":
            return data["content"][0]["text"]
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Escribir la cadena en `ai/__init__.py`**

```python
"""La cadena de motores: el orden es la prioridad, y estar en la lista es el interruptor."""

from __future__ import annotations

from ..config import Config
from .base import Analysis, AnalysisError, Engine, EngineError, analyze


class AllEnginesFailed(Exception):
    """Ninguno de los motores de la cadena pudo analizar la página."""


def build_engine(name: str, cfg: Config) -> Engine:
    options = dict(cfg.engines.get(name, {}))
    if name == "opencode":
        from .opencode import OpenCodeEngine
        return OpenCodeEngine(model=options.get("model", "opencode/ling-3.1-flash-free"))
    if name == "ollama":
        from .ollama import OllamaEngine
        return OllamaEngine(
            model=options.get("model", "qwen2.5:7b"),
            url=options.get("url", "http://localhost:11434"),
        )
    if name == "api":
        from .api import ApiEngine
        return ApiEngine(
            provider=options.get("provider", "anthropic"),
            model=options.get("model", "claude-sonnet-5"),
            key_env=options.get("key_env", ""),
            key=options.get("key", ""),
            base_url=options.get("base_url", ""),
        )
    if name == "fake":
        from .fake import FakeEngine
        return FakeEngine(options.get("replies", []))
    raise EngineError(f"unknown engine: {name!r}")


def analyze_with_chain(cfg: Config, text: str, meta: dict, known,
                       engine: str | None = None) -> tuple[Analysis, str]:
    names = (engine,) if engine else cfg.chain
    failures = []
    for name in names:
        try:
            return analyze(build_engine(name, cfg), text, meta, known, cfg.language), name
        except (EngineError, AnalysisError) as error:
            failures.append(f"{name}: {error}")
    raise AllEnginesFailed("; ".join(failures))
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_engines.py -v`
Expected: PASS, 9 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/ai tests/test_engines.py
git commit -m "feat: opencode, ollama and api engines behind one chain"
```

---

### Task 7: Descarga y extracción de artículos

**Files:**
- Modify: `src/oknowledge/model.py`
- Create: `src/oknowledge/net.py`
- Create: `src/oknowledge/extract/__init__.py`
- Create: `src/oknowledge/extract/article.py`
- Create: `tests/fixtures/article.html`
- Test: `tests/test_extract_article.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `Extracted` (dataclass con `title`, `text`, `type`, `source`, `author`, `published`, `cover_url`), `Unreadable`, `net.fetch(url) -> Fetched` (con `.status`, `.content_type`, `.content: bytes`, `.text: str`, `.final_url`), `net.NetworkError`, `detect_type(url) -> str`, `article.from_html(html, url) -> Extracted`.

- [ ] **Step 1: Escribir la página de prueba**

`tests/fixtures/article.html` — una página con todo lo que no queremos, para comprobar que no se cuela:

```html
<!doctype html>
<html lang="en">
<head>
  <title>WireGuard vs OpenVPN | Ars Technica</title>
  <meta property="og:title" content="WireGuard vs OpenVPN">
  <meta property="og:image" content="https://cdn.example.com/wg.jpg">
  <meta name="author" content="Dan Goodin">
  <meta property="article:published_time" content="2026-09-28T10:00:00Z">
</head>
<body>
  <nav><a href="/">Home</a><a href="/tech">Tech</a><a href="/sub">Subscribe now</a></nav>
  <aside class="ad">Buy our VPN today, only 2.99 a month</aside>
  <article>
    <h1>WireGuard vs OpenVPN</h1>
    <p>WireGuard runs inside the kernel, which is the main reason it moves
    data faster than OpenVPN on the same hardware.</p>
    <p>OpenVPN still wins where you need to cross hostile middleboxes, because
    it can hide inside a TLS session on port 443.</p>
  </article>
  <footer>Copyright 2026. All rights reserved. Cookie preferences.</footer>
</body>
</html>
```

- [ ] **Step 2: Escribir el test que falla**

`tests/test_extract_article.py`:

```python
from pathlib import Path

import pytest

from oknowledge.extract import Unreadable, detect_type
from oknowledge.extract.article import from_html

FIXTURE = Path(__file__).parent / "fixtures" / "article.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


def test_the_article_text_comes_out_and_the_chrome_does_not(html):
    out = from_html(html, "https://arstechnica.com/vpn")
    assert "runs inside the kernel" in out.text
    assert "hostile middleboxes" in out.text
    assert "Subscribe now" not in out.text
    assert "only 2.99 a month" not in out.text
    assert "Cookie preferences" not in out.text


def test_the_metadata_comes_out(html):
    out = from_html(html, "https://arstechnica.com/vpn")
    assert out.title == "WireGuard vs OpenVPN"
    assert out.author == "Dan Goodin"
    assert out.published == "2026-09-28"
    assert out.cover_url == "https://cdn.example.com/wg.jpg"
    assert out.source == "arstechnica.com"
    assert out.type == "article"


def test_a_page_with_no_text_is_unreadable():
    with pytest.raises(Unreadable):
        from_html("<html><body><nav>menu</nav></body></html>", "https://e.com/x")


@pytest.mark.parametrize("url,expected", [
    ("https://arstechnica.com/vpn", "article"),
    ("https://www.youtube.com/watch?v=abc", "youtube"),
    ("https://youtu.be/abc", "youtube"),
    ("https://github.com/sst/opencode", "github"),
    ("https://github.com/sst/opencode/issues/4", "github"),
    ("https://example.com/paper.pdf", "pdf"),
    ("https://example.com/paper.PDF?x=1", "pdf"),
    ("https://www.reddit.com/r/linux/comments/x/y/", "social"),
    ("https://x.com/user/status/1", "social"),
    ("https://twitter.com/user/status/1", "social"),
    ("https://www.instagram.com/p/abc/", "social"),
    ("https://www.tiktok.com/@u/video/1", "social"),
])
def test_the_type_is_guessed_from_the_url(url, expected):
    assert detect_type(url) == expected
```

- [ ] **Step 3: Correrlo y ver que falla**

Run: `pytest tests/test_extract_article.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.extract'`

- [ ] **Step 4: Agregar `Extracted` a `model.py`**

```python
@dataclass
class Extracted:
    """Lo que se le sacó a una URL antes de que la IA la lea."""

    title: str
    text: str
    type: str
    source: str
    author: str | None = None
    published: str | None = None     # YYYY-MM-DD
    cover_url: str | None = None
```

- [ ] **Step 5: Escribir `net.py`**

```python
"""Lo único que toca la red. Ningún test entra acá."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) oknowledge/0.1"


class NetworkError(Exception):
    """No se pudo traer la página."""


@dataclass
class Fetched:
    status: int
    content_type: str
    content: bytes
    final_url: str

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def fetch(url: str, timeout: float = 30.0, max_bytes: int = MAX_BYTES) -> Fetched:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es,en;q=0.8"}
    try:
        with httpx.stream("GET", url, headers=headers, timeout=timeout,
                          follow_redirects=True) as response:
            if response.status_code >= 400:
                raise NetworkError(f"{response.status_code} for {url}")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise NetworkError(f"page over {max_bytes} bytes: {url}")
                chunks.append(chunk)
            return Fetched(
                status=response.status_code,
                content_type=response.headers.get("content-type", ""),
                content=b"".join(chunks),
                final_url=str(response.url),
            )
    except NetworkError:
        raise
    except Exception as error:
        raise NetworkError(f"could not fetch {url}: {error}") from error
```

- [ ] **Step 6: Escribir `extract/__init__.py` y `extract/article.py`**

`src/oknowledge/extract/__init__.py`:

```python
"""De una URL a texto. Un extractor por tipo, elegido por la URL."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..model import Extracted

__all__ = ["Extracted", "Unreadable", "detect_type", "extract"]

SOCIAL_HOSTS = {
    "reddit.com", "x.com", "twitter.com", "instagram.com", "tiktok.com",
    "threads.net", "bsky.app",
}


class Unreadable(Exception):
    """Se llegó a la página pero no se le pudo sacar texto."""


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def detect_type(url: str) -> str:
    host = _host(url)
    path = urlsplit(url).path.lower()
    if host in {"youtube.com", "youtu.be", "m.youtube.com"}:
        return "youtube"
    if host == "github.com":
        return "github"
    if path.endswith(".pdf"):
        return "pdf"
    if host in SOCIAL_HOSTS or host.endswith(".reddit.com"):
        return "social"
    return "article"


def extract(url: str) -> Extracted:
    """Trae la URL y la convierte en texto. Es la puerta que usa el pipeline."""
    kind = detect_type(url)
    if kind == "youtube":
        from .youtube import from_url
        return from_url(url)
    if kind == "github":
        from .github import from_url
        return from_url(url)
    if kind == "pdf":
        from .pdf import from_url
        return from_url(url)
    if kind == "social":
        from .social import from_url
        return from_url(url)
    from .article import from_url
    return from_url(url)
```

`src/oknowledge/extract/article.py`:

```python
"""Páginas HTML comunes, vía trafilatura."""

from __future__ import annotations

import trafilatura

from ..model import Extracted
from ..net import fetch
from . import Unreadable, _host

MIN_CHARS = 200


def from_html(html: str, url: str) -> Extracted:
    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=True, favor_precision=True,
    )
    if not text or len(text.strip()) < MIN_CHARS:
        raise Unreadable(f"no readable text in {url}")

    meta = trafilatura.extract_metadata(html, default_url=url)
    published = (meta.date or "")[:10] if meta and meta.date else None
    return Extracted(
        title=(meta.title if meta and meta.title else url).strip(),
        text=text.strip(),
        type="article",
        source=_host(url),
        author=(meta.author.strip() if meta and meta.author else None),
        published=published or None,
        cover_url=(meta.image if meta and meta.image else None),
    )


def from_url(url: str) -> Extracted:
    return from_html(fetch(url).text, url)
```

Nota para quien implemente: `MIN_CHARS = 200` es el umbral que separa "esta página no tiene texto" de "esta página es corta". El test del fixture tiene bastante más; la página vacía del tercer test tiene cero.

- [ ] **Step 7: Correr los tests**

Run: `pytest tests/test_extract_article.py -v`
Expected: PASS, 15 tests (3 + 12 del parametrize)

- [ ] **Step 8: Commit**

```bash
git add src/oknowledge/net.py src/oknowledge/extract src/oknowledge/model.py tests/fixtures/article.html tests/test_extract_article.py
git commit -m "feat: fetch pages and extract article text"
```

---

### Task 8: YouTube, GitHub, PDF y redes sociales

**Files:**
- Create: `src/oknowledge/extract/youtube.py`
- Create: `src/oknowledge/extract/github.py`
- Create: `src/oknowledge/extract/pdf.py`
- Create: `src/oknowledge/extract/social.py`
- Create: `tests/fixtures/ytdlp.json`, `tests/fixtures/captions.vtt`, `tests/fixtures/github_repo.json`, `tests/fixtures/reddit.json`
- Modify: `pyproject.toml` (agregar `reportlab` a las dependencias de desarrollo, para fabricar un PDF de prueba)
- Test: `tests/test_extract_others.py`

**Interfaces:**
- Consumes: `Extracted`, `Unreadable`, `_host` de Task 7; `net.fetch`.
- Produces: `youtube.from_ytdlp(data, url, captions) -> Extracted`, `youtube.vtt_to_text(vtt) -> str`, `github.from_api(repo, readme, url) -> Extracted`, `pdf.from_bytes(data, url) -> Extracted`, `social.from_reddit(data, url) -> Extracted`, y un `from_url(url)` en cada uno.

- [ ] **Step 1: Escribir los fixtures**

`tests/fixtures/ytdlp.json`:

```json
{
  "title": "Cómo funciona WireGuard",
  "channel": "Redes en 10",
  "description": "Explicación corta del protocolo y de por qué es rápido.",
  "upload_date": "20260915",
  "duration": 612,
  "thumbnail": "https://i.ytimg.com/vi/abc/hq.jpg",
  "automatic_captions": {
    "es": [
      {"ext": "json3", "url": "https://example.com/captions.json3"},
      {"ext": "vtt", "url": "https://example.com/captions.vtt"}
    ]
  }
}
```

`tests/fixtures/captions.vtt`:

```text
WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:04.000
Hola, hoy vemos cómo funciona WireGuard

00:00:04.000 --> 00:00:07.500
<c>y por qué</c> es más rápido que OpenVPN
```

`tests/fixtures/github_repo.json`:

```json
{
  "full_name": "sst/opencode",
  "description": "AI coding agent, built for the terminal",
  "language": "TypeScript",
  "stargazers_count": 31245,
  "topics": ["ai", "cli"],
  "owner": {"login": "sst"},
  "pushed_at": "2026-09-30T12:00:00Z"
}
```

`tests/fixtures/reddit.json`:

```json
[
  {"data": {"children": [{"data": {
    "title": "Why I moved from OpenVPN to WireGuard",
    "selftext": "Después de dos años con OpenVPN, cambié a WireGuard y la latencia bajó a la mitad.",
    "author": "someone",
    "created_utc": 1789000000,
    "subreddit": "linux"
  }}]}},
  {"data": {"children": [
    {"data": {"body": "Lo mismo me pasó en una Raspberry Pi."}},
    {"data": {"body": "Ojo con el MTU."}}
  ]}}
]
```

- [ ] **Step 2: Escribir el test que falla**

`tests/test_extract_others.py`:

```python
import json
from pathlib import Path

import pytest

from oknowledge.extract import Unreadable
from oknowledge.extract import github, pdf, social, youtube

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_a_youtube_video_becomes_title_channel_description_and_transcript():
    out = youtube.from_ytdlp(
        load("ytdlp.json"),
        "https://youtube.com/watch?v=abc",
        captions=(FIXTURES / "captions.vtt").read_text(encoding="utf-8"),
    )
    assert out.title == "Cómo funciona WireGuard"
    assert out.author == "Redes en 10"
    assert out.published == "2026-09-15"
    assert out.type == "youtube"
    assert out.cover_url == "https://i.ytimg.com/vi/abc/hq.jpg"
    assert "Explicación corta" in out.text
    assert "cómo funciona WireGuard" in out.text
    assert "más rápido que OpenVPN" in out.text


def test_the_transcript_loses_timestamps_tags_and_repeats():
    vtt = (FIXTURES / "captions.vtt").read_text(encoding="utf-8")
    text = youtube.vtt_to_text(vtt)
    assert "-->" not in text
    assert "WEBVTT" not in text
    assert "<c>" not in text
    assert text.startswith("Hola, hoy vemos")


def test_a_video_without_transcript_still_gives_a_note():
    out = youtube.from_ytdlp(load("ytdlp.json"), "https://youtube.com/watch?v=abc", captions=None)
    assert "Explicación corta" in out.text
    assert out.title == "Cómo funciona WireGuard"


def test_a_video_with_neither_transcript_nor_description_is_unreadable():
    data = dict(load("ytdlp.json"), description="")
    with pytest.raises(Unreadable):
        youtube.from_ytdlp(data, "https://youtube.com/watch?v=abc", captions=None)


def test_a_github_repo_becomes_description_facts_and_readme():
    out = github.from_api(
        load("github_repo.json"),
        "# opencode\n\nCorre en la terminal y no necesita API key.\n",
        "https://github.com/sst/opencode",
    )
    assert out.title == "sst/opencode"
    assert out.type == "github"
    assert out.author == "sst"
    assert "AI coding agent" in out.text
    assert "TypeScript" in out.text
    assert "31245" in out.text or "31,245" in out.text
    assert "no necesita API key" in out.text


def test_a_repo_without_readme_uses_what_it_has():
    out = github.from_api(load("github_repo.json"), "", "https://github.com/sst/opencode")
    assert "AI coding agent" in out.text


def test_a_pdf_becomes_text(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "paper.pdf"
    page = canvas.Canvas(str(path))
    page.drawString(72, 720, "Resultados del experimento")
    page.drawString(72, 700, "La latencia bajo a la mitad")
    page.save()

    out = pdf.from_bytes(path.read_bytes(), "https://e.com/paper.pdf")
    assert "Resultados del experimento" in out.text
    assert "latencia" in out.text
    assert out.type == "pdf"
    assert out.title == "paper.pdf"


def test_a_pdf_with_no_text_layer_is_unreadable():
    with pytest.raises(Unreadable):
        pdf.from_bytes(b"%PDF-1.4\n%%EOF\n", "https://e.com/scan.pdf")


def test_a_reddit_thread_becomes_post_plus_comments():
    out = social.from_reddit(load("reddit.json"), "https://reddit.com/r/linux/comments/x/y/")
    assert out.title == "Why I moved from OpenVPN to WireGuard"
    assert out.type == "social"
    assert "la latencia bajó a la mitad" in out.text
    assert "Raspberry Pi" in out.text


def test_a_network_that_blocks_us_is_unreadable_not_a_crash(monkeypatch):
    from oknowledge import net

    def boom(url, **kwargs):
        raise net.NetworkError("403")

    monkeypatch.setattr("oknowledge.extract.social.fetch", boom)
    with pytest.raises(Unreadable):
        social.from_url("https://x.com/user/status/1")
```

- [ ] **Step 3: Correrlo y ver que falla**

```bash
~/.local/share/oknowledge/venv/bin/pip install -q reportlab
```

Run: `pytest tests/test_extract_others.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.extract.youtube'`

- [ ] **Step 4: Escribir los cuatro extractores**

`src/oknowledge/extract/youtube.py`:

```python
"""YouTube, vía el yt-dlp del sistema.

No se instala en el venv a propósito: yt-dlp se rompe cada vez que YouTube
cambia algo, y el del sistema se actualiza con Omarchy.
"""

from __future__ import annotations

import json
import re
import subprocess

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

CAPTION_LANGS = ("es", "es-419", "en", "en-US")


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return " ".join(lines)


def _caption_url(data: dict) -> str | None:
    tracks = {**(data.get("subtitles") or {}), **(data.get("automatic_captions") or {})}
    for lang in CAPTION_LANGS:
        for track in tracks.get(lang, []):
            if track.get("ext") == "vtt" and track.get("url"):
                return track["url"]
    return None


def from_ytdlp(data: dict, url: str, captions: str | None) -> Extracted:
    parts = [data.get("description") or ""]
    if captions:
        parts.append(vtt_to_text(captions))
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if not text:
        raise Unreadable(f"the video has neither description nor captions: {url}")

    date = str(data.get("upload_date") or "")
    published = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else None
    return Extracted(
        title=(data.get("title") or url).strip(),
        text=text,
        type="youtube",
        source=_host(url),
        author=(data.get("channel") or data.get("uploader") or None),
        published=published,
        cover_url=data.get("thumbnail"),
    )


def from_url(url: str) -> Extracted:
    try:
        proc = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", "--skip-download", url],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise Unreadable(f"yt-dlp could not read {url}: {error}") from error
    if proc.returncode != 0:
        raise Unreadable(f"yt-dlp failed on {url}: {proc.stderr.strip()[:200]}")

    data = json.loads(proc.stdout)
    captions = None
    track = _caption_url(data)
    if track:
        try:
            captions = fetch(track).text
        except NetworkError:
            captions = None
    return from_ytdlp(data, url, captions)
```

`src/oknowledge/extract/github.py`:

```python
"""Repositorios de GitHub, vía su API pública."""

from __future__ import annotations

import base64
from urllib.parse import urlsplit

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

API = "https://api.github.com/repos"


def _slug(url: str) -> str:
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) < 2:
        raise Unreadable(f"not a repository URL: {url}")
    return f"{parts[0]}/{parts[1]}"


def from_api(repo: dict, readme: str, url: str) -> Extracted:
    facts = [
        repo.get("description") or "",
        f"Lenguaje principal: {repo.get('language') or 'desconocido'}.",
        f"Estrellas: {repo.get('stargazers_count', 0)}.",
    ]
    topics = repo.get("topics") or []
    if topics:
        facts.append("Temas: " + ", ".join(topics) + ".")
    text = "\n".join(f for f in facts if f.strip())
    if readme.strip():
        text += "\n\n" + readme.strip()
    if not text.strip():
        raise Unreadable(f"the repository has no description or readme: {url}")

    pushed = str(repo.get("pushed_at") or "")[:10] or None
    return Extracted(
        title=repo.get("full_name") or _slug(url),
        text=text,
        type="github",
        source=_host(url),
        author=(repo.get("owner") or {}).get("login"),
        published=pushed,
        cover_url=None,
    )


def from_url(url: str) -> Extracted:
    slug = _slug(url)
    try:
        import json
        repo = json.loads(fetch(f"{API}/{slug}").text)
    except (NetworkError, ValueError) as error:
        raise Unreadable(f"could not read {slug}: {error}") from error

    readme = ""
    try:
        import json
        payload = json.loads(fetch(f"{API}/{slug}/readme").text)
        readme = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
    except Exception:
        readme = ""
    return from_api(repo, readme, url)
```

`src/oknowledge/extract/pdf.py`:

```python
"""PDFs, vía pypdf. Sólo el texto que el PDF ya trae: no hay OCR."""

from __future__ import annotations

import io
from urllib.parse import unquote, urlsplit

from pypdf import PdfReader

from ..model import Extracted
from ..net import fetch
from . import Unreadable, _host

MAX_PAGES = 20


def from_bytes(data: bytes, url: str) -> Extracted:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    except Exception as error:
        raise Unreadable(f"could not read the PDF at {url}: {error}") from error

    text = "\n\n".join(p.strip() for p in pages if p.strip()).strip()
    if not text:
        raise Unreadable(f"the PDF at {url} has no text layer")

    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or url
    title = (reader.metadata.title if reader.metadata and reader.metadata.title else "") or name
    return Extracted(
        title=title.strip(),
        text=text,
        type="pdf",
        source=_host(url),
        author=(reader.metadata.author if reader.metadata else None) or None,
    )


def from_url(url: str) -> Extracted:
    return from_bytes(fetch(url).content, url)
```

`src/oknowledge/extract/social.py`:

```python
"""Redes sociales, a mejor esfuerzo.

Reddit publica su JSON y se lee bien. X, Instagram y TikTok piden login o
bloquean lectores automáticos: cuando no se puede, se levanta Unreadable y el
pipeline guarda la nota igual, con la URL y marcada como parcial.
"""

from __future__ import annotations

import json

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

MAX_COMMENTS = 20


def from_reddit(data, url: str) -> Extracted:
    try:
        post = data[0]["data"]["children"][0]["data"]
    except (KeyError, IndexError, TypeError) as error:
        raise Unreadable(f"unexpected reddit payload for {url}") from error

    parts = [post.get("selftext") or ""]
    comments = data[1]["data"]["children"] if len(data) > 1 else []
    for child in comments[:MAX_COMMENTS]:
        body = (child.get("data") or {}).get("body")
        if body:
            parts.append(f"- {body}")
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if not text:
        raise Unreadable(f"the thread has no text: {url}")

    return Extracted(
        title=post.get("title") or url,
        text=text,
        type="social",
        source=_host(url),
        author=post.get("author"),
    )


def from_url(url: str) -> Extracted:
    if "reddit.com" in _host(url):
        target = url.rstrip("/") + "/.json"
        try:
            return from_reddit(json.loads(fetch(target).text), url)
        except (NetworkError, ValueError) as error:
            raise Unreadable(f"could not read {url}: {error}") from error
    try:
        fetch(url)
    except NetworkError as error:
        raise Unreadable(f"{_host(url)} does not let us read it: {error}") from error
    raise Unreadable(f"{_host(url)} needs a logged-in browser to read")
```

- [ ] **Step 5: Agregar `reportlab` a las dependencias de desarrollo**

En `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.3", "reportlab>=4.2"]
```

- [ ] **Step 6: Correr los tests**

Run: `pytest tests/test_extract_others.py -v`
Expected: PASS, 10 tests

- [ ] **Step 7: Commit**

```bash
git add src/oknowledge/extract tests/fixtures tests/test_extract_others.py pyproject.toml
git commit -m "feat: youtube, github, pdf and social extractors"
```

---

### Task 9: La cola — estados y locks

**Files:**
- Create: `src/oknowledge/queue.py`
- Modify: `src/oknowledge/model.py`
- Test: `tests/test_queue.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `QueueEntry` (dataclass con `id`, `url`, `content`, `status`, `title`, `error`, `updated`), `Queue` (clase con `root`, `enqueue(id, url, content) -> QueueEntry`, `set_status(id, status, error=None, title=None)`, `get(id) -> QueueEntry | None`, `entries() -> list[QueueEntry]`, `unfinished() -> list[QueueEntry]`, `lock(id)` como context manager), `Locked`, `state_dir() -> Path`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_queue.py`:

```python
import os
import time

import pytest

from oknowledge.queue import Locked, Queue


def test_a_new_link_starts_pending(tmp_path):
    q = Queue(tmp_path)
    entry = q.enqueue("abc123", "https://e.com/x", "full")
    assert entry.status == "pending"
    assert q.get("abc123").url == "https://e.com/x"
    assert q.get("abc123").content == "full"


def test_the_status_moves_and_keeps_the_error(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("abc123", "https://e.com/x", "full")
    q.set_status("abc123", "partial", error="403 from the site", title="Algo")
    entry = q.get("abc123")
    assert entry.status == "partial"
    assert entry.error == "403 from the site"
    assert entry.title == "Algo"


def test_unfinished_lists_what_needs_a_retry(tmp_path):
    q = Queue(tmp_path)
    for link_id, status in [("a", "ok"), ("b", "partial"), ("c", "failed"), ("d", "pending")]:
        q.enqueue(link_id, f"https://e.com/{link_id}", "full")
        q.set_status(link_id, status)
    assert sorted(e.id for e in q.unfinished()) == ["b", "c"]


def test_entries_come_back_newest_first(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("old", "https://e.com/1", "full")
    time.sleep(0.01)
    q.enqueue("new", "https://e.com/2", "full")
    assert [e.id for e in q.entries()][0] == "new"


def test_a_second_process_cannot_take_the_same_lock(tmp_path):
    q = Queue(tmp_path)
    with q.lock("abc123"):
        with pytest.raises(Locked):
            with q.lock("abc123"):
                pass


def test_the_lock_is_released_even_if_the_work_explodes(tmp_path):
    q = Queue(tmp_path)
    with pytest.raises(ValueError):
        with q.lock("abc123"):
            raise ValueError("boom")
    with q.lock("abc123"):
        pass


def test_a_lock_left_behind_by_a_dead_process_is_taken_over(tmp_path):
    # Si la máquina se apagó a mitad de un add, el lock queda huérfano.
    q = Queue(tmp_path)
    stale = q.root / "locks" / "abc123.lock"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("999999\n", encoding="utf-8")
    os.utime(stale, (time.time() - 3600, time.time() - 3600))

    with q.lock("abc123", stale_after=900):
        pass


def test_an_unknown_id_is_none(tmp_path):
    assert Queue(tmp_path).get("nope") is None
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_queue.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.queue'`

- [ ] **Step 3: Agregar `QueueEntry` a `model.py`**

```python
@dataclass
class QueueEntry:
    """El estado de un link mientras se procesa, y después de fallar."""

    id: str
    url: str
    content: str
    status: str                      # pending | ok | partial | failed
    updated: str                     # ISO 8601 UTC
    title: str | None = None
    error: str | None = None
```

- [ ] **Step 4: Escribir `queue.py`**

```python
"""El estado de cada link, en archivos, para que el widget lo pueda leer.

Son archivos y no una base de datos por una razón concreta: el plugin de
Omarchy es QML y puede mirar una carpeta con un FolderListModel, pero no
puede abrir una base.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .model import QueueEntry

UNFINISHED = ("partial", "failed")


class Locked(Exception):
    """Otro proceso está trabajando sobre este mismo link."""


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "oknowledge"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Queue:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else state_dir()

    @property
    def dir(self) -> Path:
        return self.root / "queue"

    def _path(self, link_id: str) -> Path:
        return self.dir / f"{link_id}.json"

    def _write(self, entry: QueueEntry) -> QueueEntry:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": entry.id, "url": entry.url, "content": entry.content,
            "status": entry.status, "updated": entry.updated,
            "title": entry.title, "error": entry.error,
        }
        tmp = self._path(entry.id).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path(entry.id))
        return entry

    def enqueue(self, link_id: str, url: str, content: str) -> QueueEntry:
        return self._write(QueueEntry(
            id=link_id, url=url, content=content, status="pending", updated=_now(),
        ))

    def get(self, link_id: str) -> QueueEntry | None:
        path = self._path(link_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return QueueEntry(**data)

    def set_status(self, link_id: str, status: str, error: str | None = None,
                   title: str | None = None) -> QueueEntry | None:
        entry = self.get(link_id)
        if entry is None:
            return None
        entry.status = status
        entry.updated = _now()
        if error is not None:
            entry.error = error
        if title is not None:
            entry.title = title
        return self._write(entry)

    def entries(self) -> list[QueueEntry]:
        if not self.dir.is_dir():
            return []
        found = [self.get(p.stem) for p in self.dir.glob("*.json")]
        alive = [e for e in found if e is not None]
        return sorted(alive, key=lambda e: e.updated, reverse=True)

    def unfinished(self) -> list[QueueEntry]:
        return [e for e in self.entries() if e.status in UNFINISHED]

    @contextmanager
    def lock(self, link_id: str, stale_after: int = 900):
        path = self.root / "locks" / f"{link_id}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = time.time() - path.stat().st_mtime
            if age < stale_after:
                raise Locked(f"{link_id} is already being processed")
            path.unlink(missing_ok=True)       # lo dejó un proceso que ya no está
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(handle, f"{os.getpid()}\n".encode())
            os.close(handle)
            yield
        finally:
            path.unlink(missing_ok=True)
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_queue.py -v`
Expected: PASS, 8 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/queue.py src/oknowledge/model.py tests/test_queue.py
git commit -m "feat: per-link queue state and locks"
```

---

### Task 10: El pipeline — de una URL a una nota, pase lo que pase

Es la tarea donde se cumple la regla que manda sobre todas: **nunca se pierde un link**.

**Files:**
- Create: `src/oknowledge/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `normalize`/`link_id` (Task 2), `Note`/`write_note` (Task 3), `find_note`/`rebuild_indexes`/`categories` (Task 4), `analyze_with_chain`/`AllEnginesFailed` (Task 6), `extract`/`Unreadable` (Task 7), `Queue`/`Locked` (Task 9), `net.fetch`/`NetworkError`.
- Produces: `Result` (dataclass con `id`, `url`, `path`, `status`, `engine`, `error`, `skipped`), `add(cfg, url, content=None, engine=None, reprocess=False, queue=None) -> Result`, `retry(cfg, queue=None) -> list[Result]`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_pipeline.py`:

```python
import json

import pytest

from oknowledge.config import Config
from oknowledge.extract import Unreadable
from oknowledge.model import Extracted
from oknowledge.pipeline import add, retry
from oknowledge.queue import Queue
from oknowledge.vault import all_notes, index_path, read_note

ANSWER = json.dumps({
    "title": "WireGuard vs OpenVPN",
    "summary": "Compara ambos protocolos.",
    "points": ["Corre en el kernel"],
    "category": "Redes",
    "tags": ["vpn"],
})

PAGE = Extracted(
    title="WireGuard vs OpenVPN | Ars",
    text="WireGuard runs inside the kernel...",
    type="article",
    source="arstechnica.com",
    author="Dan Goodin",
    published="2026-09-28",
    cover_url="https://cdn.example.com/wg.jpg",
)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",), engines={"fake": {"replies": [ANSWER]}})


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "state")


def extraction(monkeypatch, result):
    def fake(url):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("oknowledge.pipeline.extract", fake)


def no_cover(monkeypatch):
    monkeypatch.setattr("oknowledge.pipeline.download_cover", lambda cfg, url, link_id: None)


def test_a_good_link_becomes_a_finished_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    result = add(cfg, "https://arstechnica.com/vpn?utm_source=wa", queue=q)

    assert result.status == "ok"
    assert result.engine == "fake"
    note = read_note(result.path)
    assert note.title == "WireGuard vs OpenVPN"
    assert note.category == "Redes"
    assert note.tags == ["vpn"]
    assert note.author == "Dan Goodin"
    assert note.body == "WireGuard runs inside the kernel..."
    assert note.url == "https://arstechnica.com/vpn"
    assert q.get(note.id).status == "ok"


def test_the_category_index_is_written_too(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert "WireGuard" in index_path(cfg, "Redes").read_text(encoding="utf-8")


def test_summary_mode_drops_the_original_text(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    result = add(cfg, "https://arstechnica.com/vpn", content="summary", queue=q)
    assert read_note(result.path).body is None


def test_a_page_we_cannot_read_still_leaves_a_note(cfg, q, monkeypatch):
    # La regla que manda sobre todas: nunca se pierde el link.
    extraction(monkeypatch, Unreadable("403 from the site"))

    result = add(cfg, "https://x.com/user/status/1", queue=q)

    assert result.status == "partial"
    note = read_note(result.path)
    assert note.url == "https://x.com/user/status/1"
    assert note.status == "partial"
    assert note.category == "Sin clasificar"
    assert note.saved
    assert q.get(note.id).status == "partial"
    assert "403" in q.get(note.id).error


def test_when_every_engine_fails_the_text_is_not_thrown_away(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg = Config(vault=cfg.vault, chain=("fake",), engines={"fake": {"replies": []}})

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "partial"
    note = read_note(result.path)
    assert note.title == "WireGuard vs OpenVPN | Ars"
    assert note.body == "WireGuard runs inside the kernel..."


def test_the_same_link_twice_does_not_duplicate(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    again = add(cfg, "https://www.arstechnica.com/vpn/?utm_source=x", queue=q)

    assert again.skipped is True
    assert len(all_notes(cfg)) == 1


def test_reprocess_rewrites_the_same_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    cfg.engines["fake"]["replies"] = [json.dumps({
        "title": "WireGuard vs OpenVPN", "summary": "Otro resumen.",
        "points": [], "category": "Redes", "tags": ["vpn"],
    })]
    second = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert second.path == first.path
    assert read_note(second.path).summary == "Otro resumen."
    assert len(all_notes(cfg)) == 1


def test_the_existing_categories_are_offered_to_the_model(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    seen = {}
    import oknowledge.pipeline as pipeline

    def spy(config, text, meta, known, engine=None):
        seen["known"] = list(known)
        from oknowledge.ai.base import Analysis
        return Analysis("T", "S", [], "Redes", ["vpn"]), "fake"

    monkeypatch.setattr(pipeline, "analyze_with_chain", spy)
    add(cfg, "https://arstechnica.com/a", queue=q)
    add(cfg, "https://arstechnica.com/b", queue=q)
    assert seen["known"] == ["Redes"]


def test_retry_finishes_what_was_left_half_done(cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("503"))
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert q.unfinished()

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["ok"]
    assert not q.unfinished()
    assert len(all_notes(cfg)) == 1


def test_a_page_too_long_for_the_model_says_so_in_the_note(cfg, q, monkeypatch):
    # El spec: "si el texto excede el límite del modelo, se recorta por el
    # principio y la nota lo deja anotado".
    from oknowledge.ai.base import DEFAULT_LIMIT

    long_page = Extracted(title="Libro entero", text="x" * (DEFAULT_LIMIT + 1),
                          type="article", source="e.com")
    extraction(monkeypatch, long_page)
    no_cover(monkeypatch)

    result = add(cfg, "https://e.com/libro", queue=q)
    note = read_note(result.path)

    assert "recort" in note.summary.lower()
    assert note.body == "x" * (DEFAULT_LIMIT + 1)       # el original se guarda entero


def test_the_cover_lands_in_attachments(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)

    class Fetched:
        content = b"\x89PNG fake bytes"
        content_type = "image/jpeg"

    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Fetched())

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)
    note = read_note(result.path)

    assert note.cover == f"../attachments/{note.id}.jpg"
    assert (cfg.attachments_dir / f"{note.id}.jpg").read_bytes() == b"\x89PNG fake bytes"
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.pipeline'`

- [ ] **Step 3: Escribir `pipeline.py`**

```python
"""De una URL a una nota. El orquestador, y el guardián de una sola regla:
pase lo que pase, el link queda guardado.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from .ai import AllEnginesFailed, analyze_with_chain
from .ai.base import DEFAULT_LIMIT
from .config import Config
from .extract import Unreadable, detect_type, extract
from .model import Extracted, Note
from .net import NetworkError, fetch
from .queue import Locked, Queue
from .urls import link_id, normalize
from .vault import categories, find_note, note_path, rebuild_indexes, write_note

UNCATEGORIZED = "Sin clasificar"
PARTIAL_SUMMARY = {
    "es": "Guardado sin analizar: la página no se pudo leer o el análisis falló. "
          "Usá `oknowledge retry` para completarlo.",
    "en": "Saved without analysis: the page could not be read or the analysis failed. "
          "Run `oknowledge retry` to finish it.",
}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
TRUNCATED = {
    "es": "\n\n(La página era más larga de lo que entra en el modelo: "
          "el resumen se hizo sobre su primera parte, pero el contenido está entero más abajo.)",
    "en": "\n\n(The page was longer than the model takes: the summary covers its "
          "first part only, but the full content is kept below.)",
}


@dataclass
class Result:
    id: str
    url: str
    path: Path | None
    status: str
    engine: str | None = None
    error: str | None = None
    skipped: bool = False


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def download_cover(cfg: Config, url: str | None, link: str) -> str | None:
    if not url:
        return None
    try:
        got = fetch(url, timeout=15.0, max_bytes=5 * 1024 * 1024)
    except NetworkError:
        return None
    suffix = EXTENSIONS.get(got.content_type.split(";")[0].strip(), ".jpg")
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
    (cfg.attachments_dir / f"{link}{suffix}").write_bytes(got.content)
    return f"../attachments/{link}{suffix}"


def _partial_note(cfg: Config, link: str, url: str, content: str,
                  page: Extracted | None) -> Note:
    return Note(
        id=link,
        url=url,
        title=(page.title if page else url),
        category=UNCATEGORIZED,
        tags=[],
        type=(page.type if page else detect_type(url)),
        source=(page.source if page else url.split("/")[2] if "//" in url else url),
        saved=_today(),
        summary=PARTIAL_SUMMARY.get(cfg.language, PARTIAL_SUMMARY["en"]),
        points=[],
        status="partial",
        content=content,
        author=(page.author if page else None),
        published=(page.published if page else None),
        body=(page.text if page and content == "full" else None),
    )


def add(cfg: Config, url: str, content: str | None = None, engine: str | None = None,
        reprocess: bool = False, queue: Queue | None = None) -> Result:
    q = queue or Queue()
    clean = normalize(url)
    link = link_id(clean)
    mode = content or cfg.default_content

    existing = find_note(cfg, link)
    if existing and not reprocess:
        path, note = existing
        return Result(id=link, url=clean, path=path, status=note.status, skipped=True)

    q.enqueue(link, clean, mode)
    try:
        with q.lock(link):
            return _process(cfg, q, link, clean, mode, engine)
    except Locked as error:
        return Result(id=link, url=clean, path=None, status="pending", error=str(error))


def _process(cfg: Config, q: Queue, link: str, url: str, mode: str,
             engine: str | None) -> Result:
    page: Extracted | None = None
    try:
        page = extract(url)
    except (Unreadable, NetworkError) as error:
        note = _partial_note(cfg, link, url, mode, None)
        path = write_note(cfg, note, cfg.language)
        rebuild_indexes(cfg)
        q.set_status(link, "partial", error=str(error), title=note.title)
        return Result(id=link, url=url, path=path, status="partial", error=str(error))

    try:
        analysis, used = analyze_with_chain(
            cfg, page.text, {"url": url, "title": page.title},
            list(categories(cfg)), engine=engine,
        )
    except AllEnginesFailed as error:
        note = _partial_note(cfg, link, url, mode, page)
        path = write_note(cfg, note, cfg.language)
        rebuild_indexes(cfg)
        q.set_status(link, "partial", error=str(error), title=note.title)
        return Result(id=link, url=url, path=path, status="partial", error=str(error))

    summary = analysis.summary
    if len(page.text) > DEFAULT_LIMIT:
        summary += TRUNCATED.get(cfg.language, TRUNCATED["en"])

    note = Note(
        id=link,
        url=url,
        title=analysis.title or page.title,
        category=analysis.category or UNCATEGORIZED,
        tags=analysis.tags,
        type=page.type,
        source=page.source,
        saved=_today(),
        summary=summary,
        points=analysis.points,
        status="ok",
        content=mode,
        author=page.author,
        published=page.published,
        cover=download_cover(cfg, page.cover_url, link),
        body=page.text if mode == "full" else None,
    )
    path = write_note(cfg, note, cfg.language)
    rebuild_indexes(cfg)
    q.set_status(link, "ok", error="", title=note.title)
    return Result(id=link, url=url, path=path, status="ok", engine=used)


def retry(cfg: Config, queue: Queue | None = None) -> list[Result]:
    q = queue or Queue()
    return [add(cfg, entry.url, content=entry.content, reprocess=True, queue=q)
            for entry in q.unfinished()]
```

- [ ] **Step 4: Correr los tests**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Correr todo**

Run: `pytest -v`
Expected: PASS, 100 tests

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/pipeline.py tests/test_pipeline.py
git commit -m "feat: the pipeline, and never losing a link"
```

---

### Task 11: El CLI — `add`, `status`, `reindex`, `retry`

**Files:**
- Create: `src/oknowledge/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `config.load`/`ConfigError` (Task 1), `pipeline.add`/`pipeline.retry`/`Result` (Task 10), `vault.rebuild_indexes`/`all_notes` (Task 4), `Queue` (Task 9).
- Produces: `main(argv: list[str] | None = None) -> int`. Salida legible en inglés por defecto; `--json` imprime un objeto por línea para el plugin.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_cli.py`:

```python
import json

import pytest

from oknowledge.cli import main
from oknowledge.config import Config, ConfigError
from oknowledge.pipeline import Result


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: config)
    return config


def test_add_prints_where_the_note_landed(cfg, monkeypatch, capsys):
    monkeypatch.setattr(
        "oknowledge.cli.add",
        lambda config, url, **kw: Result(id="a1", url=url, path=cfg.links_dir / "n.md",
                                         status="ok", engine="opencode"),
    )
    assert main(["add", "https://e.com/x"]) == 0
    assert "n.md" in capsys.readouterr().out


def test_add_json_is_one_object_for_the_plugin(cfg, monkeypatch, capsys):
    monkeypatch.setattr(
        "oknowledge.cli.add",
        lambda config, url, **kw: Result(id="a1", url=url, path=cfg.links_dir / "n.md",
                                         status="ok", engine="opencode"),
    )
    main(["add", "https://e.com/x", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"id": "a1", "url": "https://e.com/x", "status": "ok",
                       "engine": "opencode", "path": str(cfg.links_dir / "n.md"),
                       "error": None, "skipped": False}


def test_the_content_flags_reach_the_pipeline(cfg, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "oknowledge.cli.add",
        lambda config, url, **kw: seen.update(kw) or Result(id="a1", url=url, path=None, status="ok"),
    )
    main(["add", "https://e.com/x", "--summary", "--engine", "ollama"])
    assert seen["content"] == "summary"
    assert seen["engine"] == "ollama"


def test_a_partial_result_exits_nonzero_so_a_script_notices(cfg, monkeypatch):
    monkeypatch.setattr(
        "oknowledge.cli.add",
        lambda config, url, **kw: Result(id="a1", url=url, path=None, status="partial",
                                         error="403"),
    )
    assert main(["add", "https://e.com/x"]) == 1


def test_status_json_lists_the_queue(cfg, monkeypatch, capsys):
    from oknowledge.model import QueueEntry

    monkeypatch.setattr(
        "oknowledge.cli.Queue",
        lambda: type("Q", (), {
            "entries": lambda self: [QueueEntry(id="a1", url="https://e.com/x",
                                                content="full", status="partial",
                                                updated="2026-10-03T10:00:00+00:00",
                                                title="X", error="403")],
        })(),
    )
    main(["status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "partial"
    assert payload[0]["title"] == "X"


def test_reindex_says_how_many_indexes_it_wrote(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.rebuild_indexes", lambda config: ["a", "b"])
    assert main(["reindex"]) == 0
    assert "2" in capsys.readouterr().out


def test_a_missing_config_is_explained_not_a_traceback(monkeypatch, capsys):
    def boom(path=None):
        raise ConfigError("no config file at /x/config.toml")

    monkeypatch.setattr("oknowledge.cli.load_config", boom)
    assert main(["status"]) == 2
    assert "no config file" in capsys.readouterr().err


def test_no_subcommand_prints_help(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.cli'`

- [ ] **Step 3: Escribir `cli.py`**

```python
"""La puerta de entrada. El plugin de Omarchy habla con el sistema por acá.

Los mensajes van en inglés: son respuestas para scripts, no texto de interfaz.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .config import CONFIG_PATH, ConfigError
from .config import load as load_config
from .pipeline import Result, add, retry
from .queue import Queue
from .vault import all_notes, rebuild_indexes


def _result_dict(result: Result) -> dict:
    data = dataclasses.asdict(result)
    data["path"] = str(result.path) if result.path else None
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oknowledge")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    subs = parser.add_subparsers(dest="command")

    add_cmd = subs.add_parser("add", help="save a link")
    add_cmd.add_argument("url")
    group = add_cmd.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true", help="keep the original text")
    group.add_argument("--summary", action="store_true", help="keep only the summary")
    add_cmd.add_argument("--engine", help="force one engine for this link")
    add_cmd.add_argument("--reprocess", action="store_true")
    add_cmd.add_argument("--json", action="store_true")

    status = subs.add_parser("status", help="what is pending or failed")
    status.add_argument("--json", action="store_true")

    subs.add_parser("reindex", help="rebuild the category indexes")

    retry_cmd = subs.add_parser("retry", help="finish the links left half done")
    retry_cmd.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    try:
        cfg = load_config(args.config)
    except ConfigError as error:
        print(f"oknowledge: {error}", file=sys.stderr)
        return 2

    if args.command == "add":
        content = "summary" if args.summary else ("full" if args.full else None)
        result = add(cfg, args.url, content=content, engine=args.engine,
                     reprocess=args.reprocess)
        if args.json:
            print(json.dumps(_result_dict(result), ensure_ascii=False))
        elif result.skipped:
            print(f"already saved: {result.path}")
        elif result.status == "ok":
            print(f"saved: {result.path}")
        else:
            print(f"saved incomplete ({result.error}): {result.path}", file=sys.stderr)
        return 0 if result.status == "ok" or result.skipped else 1

    if args.command == "status":
        entries = Queue().entries()
        if args.json:
            print(json.dumps([dataclasses.asdict(e) for e in entries], ensure_ascii=False))
        else:
            print(f"{len(all_notes(cfg))} notes")
            for entry in entries:
                if entry.status != "ok":
                    print(f"  {entry.status:8} {entry.title or entry.url}")
        return 0

    if args.command == "reindex":
        written = rebuild_indexes(cfg)
        print(f"{len(written)} indexes rewritten")
        return 0

    if args.command == "retry":
        results = retry(cfg)
        if args.json:
            print(json.dumps([_result_dict(r) for r in results], ensure_ascii=False))
        else:
            print(f"{sum(1 for r in results if r.status == 'ok')}/{len(results)} finished")
        return 0

    return 2
```

- [ ] **Step 4: Correr los tests**

Run: `pytest tests/test_cli.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Probarlo a mano contra el vault real**

```bash
mkdir -p ~/.config/oknowledge
cat > ~/.config/oknowledge/config.toml <<'EOF'
vault = "/home/fer/Documents/obsidian_vaults/fer"

[ai]
chain = ["opencode"]
language = "es"

[ai.opencode]
model = "opencode/ling-3.1-flash-free"
EOF
chmod 600 ~/.config/oknowledge/config.toml

~/.local/share/oknowledge/venv/bin/oknowledge add https://omarchy.org/ --summary
~/.local/share/oknowledge/venv/bin/oknowledge status
```

Expected: una nota nueva en `oknowledge/links/` y un índice en `oknowledge/`. Abrir la nota en Obsidian y leerla.

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/cli.py tests/test_cli.py
git commit -m "feat: the command line: add, status, reindex, retry"
```

---

### Task 12: La web que se lee — índice en memoria, biblioteca, búsqueda y ficha

**Files:**
- Create: `src/oknowledge/i18n.py`
- Create: `src/oknowledge/web/__init__.py`
- Create: `src/oknowledge/web/index.py`
- Create: `src/oknowledge/web/app.py`
- Create: `src/oknowledge/web/templates/base.html`, `library.html`, `item.html`
- Create: `src/oknowledge/web/static/style.css`
- Test: `tests/test_i18n.py`, `tests/test_web_read.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `all_notes`/`categories`/`find_note` (Task 4), `Note` (Task 3).
- Produces: `i18n.ui_language() -> str`, `i18n.translator(lang) -> Callable[[str], str]`, `index.Library` (clase con `notes`, `refresh()`, `by_id(id)`, `filter(category=None, tag=None)`, `search(query) -> list[Hit]`, `tags() -> dict[str, int]`, `categories() -> dict[str, int]`), `Hit` (dataclass con `note` y `snippet`), `web.app.create_app(cfg) -> FastAPI`.

- [ ] **Step 1: Escribir el test del idioma**

`tests/test_i18n.py`:

```python
import json

from oknowledge import i18n


def write_pref(tmp_path, content):
    path = tmp_path / "plugin-language.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_without_the_file_everything_is_english(tmp_path):
    assert i18n.ui_language(tmp_path / "nope.json") == "en"


def test_the_shared_file_switches_the_interface(tmp_path):
    path = write_pref(tmp_path, json.dumps({"language": "es"}))
    assert i18n.ui_language(path) == "es"


def test_a_broken_file_falls_back_quietly(tmp_path):
    assert i18n.ui_language(write_pref(tmp_path, "{no json")) == "en"


def test_a_language_we_do_not_have_falls_back(tmp_path):
    assert i18n.ui_language(write_pref(tmp_path, json.dumps({"language": "fr"}))) == "en"


def test_english_is_the_identity():
    t = i18n.translator("en")
    assert t("Search") == "Search"
    assert t("No results") == "No results"


def test_spanish_translates_what_it_knows_and_passes_through_the_rest():
    t = i18n.translator("es")
    assert t("Search") == "Buscar"
    assert t("Categories") == "Categorías"
    assert t("a string nobody translated") == "a string nobody translated"
```

- [ ] **Step 2: Escribir `i18n.py`**

```python
"""El idioma de la interfaz: inglés por defecto, español opcional.

La preferencia no es de este proyecto: vive en el archivo compartido de
Omarchy y la usan todos mis plugins. El texto en inglés es la clave, así que
una traducción que falta se degrada al inglés y nada se rompe.
"""

from __future__ import annotations

import json
from pathlib import Path

SHARED_FILE = Path.home() / ".config" / "omarchy" / "plugin-language.json"
LANGUAGES = ("en", "es")

STRINGS = {
    "es": {
        "Library": "Biblioteca",
        "Search": "Buscar",
        "Search your library": "Buscá en tu biblioteca",
        "Categories": "Categorías",
        "Settings": "Ajustes",
        "No results": "Sin resultados",
        "Nothing saved yet": "Todavía no guardaste nada",
        "%1 links": "%1 links",
        "Open original": "Abrir el original",
        "Key points": "Puntos clave",
        "Original content": "Contenido original",
        "Saved": "Guardado",
        "Incomplete": "Incompleto",
        "Retry": "Reintentar",
        "Delete": "Borrar",
        "Reprocess": "Reprocesar",
        "Edit tags": "Editar etiquetas",
        "Move to category": "Mover a categoría",
        "Rename": "Renombrar",
        "Merge into": "Fusionar con",
        "Save": "Guardar",
        "Cancel": "Cancelar",
        "Engines": "Motores",
        "Interface language": "Idioma de la interfaz",
        "Summary language": "Idioma de los resúmenes",
        "Keep by default": "Guardar por defecto",
        "All": "Todo",
    },
}


def ui_language(path: Path | None = None) -> str:
    target = Path(path) if path else SHARED_FILE
    try:
        value = json.loads(target.read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return "en"
    return value if value in LANGUAGES else "en"


def translator(language: str):
    table = STRINGS.get(language, {})

    def t(text: str, *args) -> str:
        out = table.get(text, text)
        for n, value in enumerate(args, start=1):
            out = out.replace(f"%{n}", str(value))
        return out

    return t
```

- [ ] **Step 3: Escribir el test de la web que falla**

`tests/test_web_read.py`:

```python
import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title, category, tags, summary, body=None, saved="2026-10-03"):
    return Note(
        id=id, url=f"https://e.com/{id}", title=title, category=category, tags=list(tags),
        type="article", source="e.com", saved=saved, summary=summary,
        points=["un punto"], body=body,
    )


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard vs OpenVPN", "Redes", ["vpn"],
                         "Compara ambos protocolos.",
                         body="El kernel hace la diferencia."), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina", ["pan"],
                         "Cómo arrancar una masa madre.", saved="2026-09-20"), "es")
    rebuild_indexes(cfg)
    return TestClient(create_app(cfg))


def test_the_library_shows_every_note_newest_first(client):
    body = client.get("/").text
    assert "WireGuard vs OpenVPN" in body
    assert "Masa madre" in body
    assert body.index("WireGuard") < body.index("Masa madre")


def test_the_library_filters_by_category(client):
    body = client.get("/?category=Cocina").text
    assert "Masa madre" in body
    assert "WireGuard" not in body


def test_the_library_filters_by_tag(client):
    body = client.get("/?tag=vpn").text
    assert "WireGuard" in body
    assert "Masa madre" not in body


def test_search_looks_inside_the_summary(client):
    body = client.get("/search?q=protocolos").text
    assert "WireGuard" in body
    assert "Masa madre" not in body


def test_search_looks_inside_the_saved_content(client):
    body = client.get("/search?q=kernel").text
    assert "WireGuard" in body


def test_search_shows_the_fragment_where_it_matched(client):
    body = client.get("/search?q=kernel").text
    assert "kernel hace la diferencia" in body


def test_search_ignores_case_and_accents(client):
    assert "Masa madre" in client.get("/search?q=COMO").text


def test_search_with_no_hits_says_so(client):
    assert "No results" in client.get("/search?q=zzzz").text


def test_an_item_page_shows_the_summary_the_points_and_the_link(client):
    body = client.get("/item/a1").text
    assert "Compara ambos protocolos." in body
    assert "un punto" in body
    assert "https://e.com/a1" in body


def test_an_unknown_item_is_a_404(client):
    assert client.get("/item/zzzz").status_code == 404


def test_the_interface_follows_the_shared_language_file(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    monkeypatch.setattr("oknowledge.web.app.ui_language", lambda: "es")
    body = TestClient(create_app(Config(vault=vault))).get("/").text
    assert "Buscá en tu biblioteca" in body
```

- [ ] **Step 4: Correrlo y ver que falla**

Run: `pytest tests/test_web_read.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.web'`

- [ ] **Step 5: Escribir `web/index.py`**

```python
"""El índice que sirve la web: las notas del vault, en memoria.

No hay base de datos. Con unos cientos de notas, leer el vault entero y
guardarlo en una lista es instantáneo, y cualquier edición hecha en Obsidian
aparece apenas se refresca.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..config import Config
from ..model import Note
from ..vault import all_notes

SNIPPET = 160


def fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return plain.lower()


@dataclass
class Hit:
    note: Note
    snippet: str


class Library:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.notes: list[Note] = []
        self.refresh()

    def refresh(self) -> None:
        self.notes = sorted(all_notes(self.cfg), key=lambda n: (n.saved, n.title), reverse=True)

    def by_id(self, link_id: str) -> Note | None:
        return next((n for n in self.notes if n.id == link_id), None)

    def filter(self, category: str | None = None, tag: str | None = None) -> list[Note]:
        found = self.notes
        if category:
            found = [n for n in found if n.category == category]
        if tag:
            found = [n for n in found if tag in n.tags]
        return found

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self.notes:
            counts[note.category] = counts.get(note.category, 0) + 1
        return dict(sorted(counts.items()))

    def tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self.notes:
            for tag in note.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def search(self, query: str) -> list[Hit]:
        needle = fold(query).strip()
        if not needle:
            return []
        hits = []
        for note in self.notes:
            haystacks = [note.title, note.summary, " ".join(note.points),
                         " ".join(note.tags), note.category, note.body or ""]
            for text in haystacks:
                position = fold(text).find(needle)
                if position != -1:
                    start = max(0, position - SNIPPET // 2)
                    piece = text[start:start + SNIPPET].strip()
                    hits.append(Hit(note=note, snippet=("…" if start else "") + piece + "…"))
                    break
        return hits
```

- [ ] **Step 6: Escribir `web/app.py`**

```python
"""La web. Lee el vault y lo muestra; en esta tarea no escribe nada."""

from __future__ import annotations

from importlib.resources import files

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Config
from ..i18n import translator, ui_language
from .index import Library

WEB = files("oknowledge").joinpath("web")


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="oknowledge", docs_url=None, redoc_url=None)
    library = Library(cfg)
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, **context) -> HTMLResponse:
        language = ui_language()
        return templates.TemplateResponse(
            request=request, name=name,
            context={"t": translator(language), "lang": language,
                     "categories": library.categories(), "tags": library.tags(), **context},
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, category: str | None = None, tag: str | None = None):
        library.refresh()
        return page(request, "library.html",
                    notes=library.filter(category=category, tag=tag),
                    category=category, tag=tag, query="")

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        library.refresh()
        return page(request, "library.html", notes=None, hits=library.search(q),
                    category=None, tag=None, query=q)

    @app.get("/item/{link_id}", response_class=HTMLResponse)
    def item(request: Request, link_id: str):
        library.refresh()
        note = library.by_id(link_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such link")
        return page(request, "item.html", note=note, query="")

    app.state.library = library
    app.state.cfg = cfg
    return app
```

- [ ] **Step 7: Escribir las plantillas y el CSS**

`src/oknowledge/web/templates/base.html`:

```html
<!doctype html>
<html lang="{{ lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>oknowledge</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <a class="brand" href="/">oknowledge</a>
    <form action="/search" method="get" role="search">
      <input type="search" name="q" value="{{ query }}"
             placeholder="{{ t('Search your library') }}" autofocus>
    </form>
    <nav>
      <a href="/categories">{{ t('Categories') }}</a>
      <a href="/settings">{{ t('Settings') }}</a>
    </nav>
  </header>
  <main>{% block main %}{% endblock %}</main>
</body>
</html>
```

`src/oknowledge/web/templates/library.html`:

```html
{% extends "base.html" %}
{% block main %}
  {% if notes is not none %}
    <div class="chips">
      <a href="/" class="chip {% if not category and not tag %}on{% endif %}">{{ t('All') }}</a>
      {% for name, count in categories.items() %}
        <a href="/?category={{ name|urlencode }}"
           class="chip {% if category == name %}on{% endif %}">{{ name }} <b>{{ count }}</b></a>
      {% endfor %}
    </div>
    <div class="chips tags">
      {% for name, count in tags.items() %}
        <a href="/?tag={{ name|urlencode }}"
           class="chip small {% if tag == name %}on{% endif %}">#{{ name }}</a>
      {% endfor %}
    </div>
    {% if not notes %}<p class="empty">{{ t('Nothing saved yet') }}</p>{% endif %}
    <ul class="grid">
      {% for note in notes %}
        <li class="card{% if note.status != 'ok' %} partial{% endif %}">
          <a href="/item/{{ note.id }}">
            {% if note.cover %}<img src="/cover/{{ note.id }}" alt="" loading="lazy">{% endif %}
            <h2>{{ note.title }}</h2>
            <p class="meta"><span class="cat">{{ note.category }}</span> · {{ note.saved }}</p>
            <p class="sum">{{ note.summary.split('\n')[0] }}</p>
            <p class="tags">{% for tag in note.tags %}<span>#{{ tag }}</span>{% endfor %}</p>
          </a>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    {% if not hits %}<p class="empty">{{ t('No results') }}</p>{% endif %}
    <ul class="hits">
      {% for hit in hits %}
        <li>
          <a href="/item/{{ hit.note.id }}">
            <h2>{{ hit.note.title }}</h2>
            <p class="meta"><span class="cat">{{ hit.note.category }}</span> · {{ hit.note.saved }}</p>
            <p class="snippet">{{ hit.snippet }}</p>
          </a>
        </li>
      {% endfor %}
    </ul>
  {% endif %}
{% endblock %}
```

`src/oknowledge/web/templates/item.html`:

```html
{% extends "base.html" %}
{% block main %}
  <article class="item">
    <p class="meta"><span class="cat">{{ note.category }}</span> · {{ note.source }} · {{ note.saved }}
      {% if note.status != 'ok' %}<span class="warn">{{ t('Incomplete') }}</span>{% endif %}</p>
    <h1>{{ note.title }}</h1>
    <p class="tags">{% for tag in note.tags %}<a href="/?tag={{ tag|urlencode }}">#{{ tag }}</a>{% endfor %}</p>
    <div class="summary">{{ note.summary }}</div>
    {% if note.points %}
      <h2>{{ t('Key points') }}</h2>
      <ul>{% for point in note.points %}<li>{{ point }}</li>{% endfor %}</ul>
    {% endif %}
    <p><a class="button" href="{{ note.url }}" rel="noreferrer">{{ t('Open original') }}</a></p>
    {% if note.body %}
      <details>
        <summary>{{ t('Original content') }}</summary>
        <pre>{{ note.body }}</pre>
      </details>
    {% endif %}
  </article>
{% endblock %}
```

`src/oknowledge/web/static/style.css` — una sola columna, sin sidebar, color sólo en la categoría:

```css
:root {
  --bg: #fbfbfa; --fg: #1a1a18; --dim: #6b6b66; --line: #e6e4df;
  --accent: #3b5bdb; --card: #ffffff;
  --measure: 46rem;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #15161a; --fg: #e9e9e6; --dim: #9a9a94; --line: #2a2c33;
          --accent: #8da2fb; --card: #1c1e24; }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
header {
  display: flex; gap: 1.5rem; align-items: center;
  max-width: var(--measure); margin: 0 auto; padding: 1.5rem 1rem;
}
.brand { font-weight: 600; text-decoration: none; color: var(--fg); letter-spacing: -0.01em; }
header form { flex: 1; }
header input {
  width: 100%; padding: 0.6rem 0.9rem; border: 1px solid var(--line);
  border-radius: 9px; background: var(--card); color: inherit; font: inherit;
}
header nav a { color: var(--dim); text-decoration: none; margin-left: 1rem; font-size: 0.9rem; }
header nav a:hover { color: var(--fg); }
main { max-width: var(--measure); margin: 0 auto; padding: 0 1rem 5rem; }

.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }
.chips.tags { margin-bottom: 2rem; }
.chip {
  padding: 0.25rem 0.7rem; border: 1px solid var(--line); border-radius: 999px;
  text-decoration: none; color: var(--dim); font-size: 0.85rem; background: var(--card);
}
.chip b { font-weight: 500; opacity: 0.6; }
.chip.small { font-size: 0.78rem; }
.chip.on { border-color: var(--accent); color: var(--accent); }

.grid { list-style: none; padding: 0; margin: 0; display: grid; gap: 1rem;
        grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
        overflow: hidden; transition: border-color 0.15s; }
.card:hover { border-color: var(--accent); }
.card.partial { border-style: dashed; }
.card a { text-decoration: none; color: inherit; display: block; padding: 1rem; }
.card img { width: calc(100% + 2rem); margin: -1rem -1rem 0.8rem; display: block;
            aspect-ratio: 16/9; object-fit: cover; }
.card h2 { font-size: 1rem; margin: 0 0 0.3rem; line-height: 1.35; }
.meta { color: var(--dim); font-size: 0.8rem; margin: 0 0 0.5rem; }
.cat { color: var(--accent); }
.warn { color: var(--dim); border: 1px solid var(--line); border-radius: 999px;
        padding: 0 0.5rem; margin-left: 0.5rem; }
.sum { margin: 0 0 0.6rem; font-size: 0.9rem; color: var(--fg); }
.tags span, .tags a { color: var(--dim); font-size: 0.78rem; margin-right: 0.4rem;
                      text-decoration: none; }

.hits { list-style: none; padding: 0; }
.hits li { border-bottom: 1px solid var(--line); }
.hits a { display: block; padding: 1.1rem 0; text-decoration: none; color: inherit; }
.hits h2 { font-size: 1.05rem; margin: 0 0 0.2rem; }
.snippet { margin: 0; color: var(--dim); font-size: 0.9rem; }

.item { padding-top: 1rem; }
.item h1 { font-size: 2rem; line-height: 1.2; margin: 0.2rem 0 0.6rem; letter-spacing: -0.02em; }
.summary { font-size: 1.15rem; line-height: 1.7; white-space: pre-wrap; margin: 1.5rem 0; }
.item h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em;
           color: var(--dim); margin-top: 2.5rem; }
.button { display: inline-block; padding: 0.5rem 1rem; border: 1px solid var(--line);
          border-radius: 9px; text-decoration: none; color: var(--fg); background: var(--card); }
details pre { white-space: pre-wrap; font: inherit; color: var(--dim); }
.empty { color: var(--dim); padding: 4rem 0; text-align: center; }
.actions { opacity: 0; transition: opacity 0.15s; }
.item:hover .actions, .actions:focus-within { opacity: 1; }
```

Falta una ruta: `/cover/{id}`, que sirve la imagen desde `attachments/`. Agregarla a `app.py`:

```python
    @app.get("/cover/{link_id}")
    def cover(link_id: str):
        from fastapi.responses import FileResponse
        note = library.by_id(link_id)
        if note is None or not note.cover:
            raise HTTPException(status_code=404, detail="no cover")
        path = (cfg.links_dir / note.cover).resolve()
        if cfg.attachments_dir.resolve() not in path.parents or not path.exists():
            raise HTTPException(status_code=404, detail="no cover")
        return FileResponse(path)
```

- [ ] **Step 8: Correr los tests**

Run: `pytest tests/test_i18n.py tests/test_web_read.py -v`
Expected: PASS, 17 tests

- [ ] **Step 9: Commit**

```bash
git add src/oknowledge/i18n.py src/oknowledge/web tests/test_i18n.py tests/test_web_read.py
git commit -m "feat: the web library, search and item pages"
```

---

### Task 13: La web que escribe — categorías, etiquetas y ajustes

**Files:**
- Modify: `src/oknowledge/vault.py`
- Modify: `src/oknowledge/config.py`
- Modify: `src/oknowledge/i18n.py`
- Modify: `src/oknowledge/web/app.py`
- Create: `src/oknowledge/web/templates/categories.html`, `settings.html`
- Modify: `pyproject.toml` (agregar `tomli-w`)
- Test: `tests/test_vault_edit.py`, `tests/test_web_write.py`

**Interfaces:**
- Consumes: todo lo de Tasks 3, 4, 12.
- Produces: `vault.update_note(cfg, link_id, language, category=None, tags=None) -> Path | None`, `vault.delete_note(cfg, link_id) -> bool`, `vault.rename_category(cfg, old, new, language) -> int`, `config.save(cfg, path)`, `i18n.set_ui_language(lang, path=None)`, y las rutas `POST /item/{id}/category`, `POST /item/{id}/tags`, `POST /item/{id}/delete`, `POST /item/{id}/reprocess`, `GET /categories`, `POST /categories/rename`, `GET /settings`, `POST /settings`.

- [ ] **Step 1: Escribir el test de edición del vault**

`tests/test_vault_edit.py`:

```python
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    delete_note, index_path, rebuild_indexes, read_note, rename_category,
    update_note, write_note,
)


def make(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def note(id, title, category, tags=("x",)):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type="article", source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


def test_moving_a_note_to_another_category_updates_both_indexes(tmp_path):
    cfg = make(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    rebuild_indexes(cfg)

    update_note(cfg, "a1", "es", category="Seguridad")

    assert not index_path(cfg, "Redes").exists()
    assert "WireGuard" in index_path(cfg, "Seguridad").read_text(encoding="utf-8")


def test_editing_tags_normalizes_them(tmp_path):
    cfg = make(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    update_note(cfg, "a1", "es", tags=["VPN", "Programación", "vpn"])
    assert read_note(path).tags == ["vpn", "programacion"]


def test_editing_does_not_lose_the_body(tmp_path):
    cfg = make(tmp_path)
    original = note("a1", "WireGuard", "Redes")
    original.body = "El texto entero."
    path = write_note(cfg, original, "es")
    update_note(cfg, "a1", "es", category="Seguridad")
    assert read_note(path).body == "El texto entero."


def test_deleting_a_note_removes_it_from_its_index(tmp_path):
    cfg = make(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "SSH", "Redes"), "es")
    rebuild_indexes(cfg)

    assert delete_note(cfg, "a1") is True

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert "WireGuard" not in text and "SSH" in text


def test_renaming_a_category_moves_every_note(tmp_path):
    cfg = make(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")
    write_note(cfg, note("b2", "SSH", "Networking"), "es")
    rebuild_indexes(cfg)

    moved = rename_category(cfg, "Networking", "Redes", "es")

    assert moved == 2
    assert not index_path(cfg, "Networking").exists()
    assert index_path(cfg, "Redes").read_text(encoding="utf-8").count("[[") == 2


def test_merging_into_an_existing_category_joins_them(tmp_path):
    cfg = make(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")
    write_note(cfg, note("b2", "Túneles", "Redes"), "es")
    rebuild_indexes(cfg)

    rename_category(cfg, "Networking", "Redes", "es")

    assert index_path(cfg, "Redes").read_text(encoding="utf-8").count("[[") == 2


def test_a_note_of_yours_is_not_dragged_into_a_rename(tmp_path):
    # Tu nota, sin marcador, con la misma categoría en el frontmatter.
    cfg = make(tmp_path)
    mine = cfg.links_dir / "mia.md"
    mine.write_text("---\ncategory: Networking\n---\n\nMía.\n", encoding="utf-8")
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")

    rename_category(cfg, "Networking", "Redes", "es")

    assert mine.read_text(encoding="utf-8") == "---\ncategory: Networking\n---\n\nMía.\n"


def test_updating_a_link_that_does_not_exist_is_none(tmp_path):
    assert update_note(make(tmp_path), "zzz", "es", category="X") is None
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_vault_edit.py -v`
Expected: FAIL con `ImportError: cannot import name 'update_note'`

- [ ] **Step 3: Agregar a `vault.py`**

```python
def update_note(cfg: Config, link_id: str, language: str,
                category: str | None = None, tags=None) -> Path | None:
    """Cambia la clasificación de una nota nuestra y rehace los índices."""
    found = find_note(cfg, link_id)
    if found is None:
        return None
    path, note = found
    if category is not None:
        note.category = category.strip() or note.category
    if tags is not None:
        from .ai.base import normalize_tags
        note.tags = normalize_tags(tags)
    path.unlink()                       # el nombre no cambia, pero el destino puede
    written = write_note(cfg, note, language)
    rebuild_indexes(cfg)
    return written


def delete_note(cfg: Config, link_id: str) -> bool:
    found = find_note(cfg, link_id)
    if found is None:
        return False
    found[0].unlink()
    rebuild_indexes(cfg)
    return True


def rename_category(cfg: Config, old: str, new: str, language: str) -> int:
    """Renombra una categoría; si `new` ya existe, las fusiona.

    Sólo toca notas nuestras: all_notes() ya descarta todo lo demás.
    """
    target = new.strip()
    if not target:
        return 0
    moved = 0
    for note in all_notes(cfg):
        if note.category != old:
            continue
        note.category = target
        found = find_note(cfg, note.id)
        if found:
            found[0].unlink()
        write_note(cfg, note, language)
        moved += 1
    rebuild_indexes(cfg)
    return moved
```

- [ ] **Step 4: Agregar `config.save` e `i18n.set_ui_language`**

En `config.py`:

```python
def save(cfg: Config, path: Path = CONFIG_PATH) -> Path:
    """Reescribe el config.toml. Los comentarios que hayas puesto se pierden."""
    import tomli_w

    data = {
        "vault": str(cfg.vault),
        "folder": cfg.folder,
        "default_content": cfg.default_content,
        "ai": {"chain": list(cfg.chain), "language": cfg.language, **cfg.engines},
        "web": {"port": cfg.port, "idle_timeout": cfg.idle_timeout},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    path.chmod(0o600)
    return path
```

En `i18n.py`:

```python
def set_ui_language(language: str, path: Path | None = None) -> Path:
    """Escribe la preferencia compartida. La cambian todos mis plugins a la vez."""
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    target = Path(path) if path else SHARED_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"language": language}) + "\n", encoding="utf-8")
    return target
```

Y en `pyproject.toml`, agregar `"tomli-w>=1.1"` a `dependencies`.

- [ ] **Step 5: Escribir el test de las rutas que escriben**

`tests/test_web_write.py`:

```python
import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import index_path, rebuild_indexes, read_note, write_note
from oknowledge.web.app import create_app


def note(id, title, category, tags=("x",)):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type="article", source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


@pytest.fixture
def setup(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")
    rebuild_indexes(cfg)
    return cfg, TestClient(create_app(cfg))


def test_moving_a_note_from_the_item_page(setup):
    cfg, client = setup
    response = client.post("/item/a1/category", data={"category": "Redes"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert index_path(cfg, "Redes").exists()


def test_editing_tags_from_the_item_page(setup):
    cfg, client = setup
    client.post("/item/a1/tags", data={"tags": "vpn, Seguridad, vpn"})
    from oknowledge.vault import find_note
    assert find_note(cfg, "a1")[1].tags == ["vpn", "seguridad"]


def test_deleting_from_the_item_page(setup):
    cfg, client = setup
    client.post("/item/a1/delete", follow_redirects=False)
    from oknowledge.vault import find_note
    assert find_note(cfg, "a1") is None


def test_the_categories_page_lists_them_with_counts(setup):
    _, client = setup
    body = client.get("/categories").text
    assert "Networking" in body and "Cocina" in body


def test_renaming_a_category_from_the_web(setup):
    cfg, client = setup
    client.post("/categories/rename", data={"old": "Networking", "new": "Redes"})
    assert index_path(cfg, "Redes").exists()
    assert not index_path(cfg, "Networking").exists()


def test_settings_shows_the_chain_and_both_languages(setup):
    _, client = setup
    body = client.get("/settings").text
    assert "opencode" in body
    assert "Interface language" in body or "Idioma de la interfaz" in body


def test_saving_settings_writes_the_config_and_the_shared_language(setup, tmp_path, monkeypatch):
    cfg, client = setup
    config_path = tmp_path / "config.toml"
    shared = tmp_path / "plugin-language.json"
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", config_path)
    monkeypatch.setattr("oknowledge.i18n.SHARED_FILE", shared)

    client.post("/settings", data={
        "chain": ["ollama", "opencode"], "language": "en",
        "default_content": "summary", "ui_language": "es",
    })

    import tomllib
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["chain"] == ["ollama", "opencode"]
    assert saved["ai"]["language"] == "en"
    assert saved["default_content"] == "summary"
    import json
    assert json.loads(shared.read_text(encoding="utf-8"))["language"] == "es"
```

- [ ] **Step 6: Agregar las rutas a `web/app.py`**

```python
from fastapi import Form
from fastapi.responses import RedirectResponse

from ..config import CONFIG_PATH, save as save_config
from ..i18n import set_ui_language
from ..pipeline import add as add_link
from ..vault import delete_note, rename_category, update_note


    @app.post("/item/{link_id}/category")
    def move(link_id: str, category: str = Form("")):
        update_note(cfg, link_id, ui_language(), category=category)
        library.refresh()
        return RedirectResponse(f"/item/{link_id}", status_code=303)

    @app.post("/item/{link_id}/tags")
    def retag(link_id: str, tags: str = Form("")):
        update_note(cfg, link_id, ui_language(),
                    tags=[t for t in tags.replace(",", " ").split() if t])
        library.refresh()
        return RedirectResponse(f"/item/{link_id}", status_code=303)

    @app.post("/item/{link_id}/delete")
    def remove(link_id: str):
        delete_note(cfg, link_id)
        library.refresh()
        return RedirectResponse("/", status_code=303)

    @app.post("/item/{link_id}/reprocess")
    def reprocess(link_id: str, engine: str = Form("")):
        note = library.by_id(link_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such link")
        add_link(cfg, note.url, engine=engine or None, reprocess=True)
        library.refresh()
        return RedirectResponse(f"/item/{link_id}", status_code=303)

    @app.get("/categories", response_class=HTMLResponse)
    def category_page(request: Request):
        library.refresh()
        return page(request, "categories.html", query="")

    @app.post("/categories/rename")
    def rename(old: str = Form(...), new: str = Form(...)):
        rename_category(cfg, old, new, ui_language())
        library.refresh()
        return RedirectResponse("/categories", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return page(request, "settings.html", cfg=cfg, ui=ui_language(), query="")

    @app.post("/settings")
    def save_settings(chain: list[str] = Form([]), language: str = Form("es"),
                      default_content: str = Form("full"),
                      ui_language_: str = Form("en", alias="ui_language"),
                      opencode_model: str = Form(""), ollama_model: str = Form(""),
                      api_model: str = Form("")):
        engines = {name: dict(options) for name, options in cfg.engines.items()}
        for name, model in (("opencode", opencode_model), ("ollama", ollama_model),
                            ("api", api_model)):
            if model.strip():
                engines.setdefault(name, {})["model"] = model.strip()
        updated = dataclasses.replace(
            cfg, chain=tuple(chain) or cfg.chain, language=language,
            default_content=default_content, engines=engines,
        )
        save_config(updated, CONFIG_PATH)
        set_ui_language(ui_language_)
        return RedirectResponse("/settings", status_code=303)
```

(`import dataclasses` arriba del archivo.)

- [ ] **Step 7: Agregar las acciones a `item.html`**

Las rutas de arriba no tienen desde dónde llamarse. Agregar este bloque al
final de `<article class="item">`, antes de cerrar:

```html
    <div class="actions">
      <form action="/item/{{ note.id }}/category" method="post" class="row">
        <input name="category" value="{{ note.category }}" list="known"
               aria-label="{{ t('Move to category') }}">
        <button type="submit">{{ t('Save') }}</button>
      </form>
      <form action="/item/{{ note.id }}/tags" method="post" class="row">
        <input name="tags" value="{{ note.tags|join(', ') }}"
               aria-label="{{ t('Edit tags') }}">
        <button type="submit">{{ t('Save') }}</button>
      </form>
      <form action="/item/{{ note.id }}/reprocess" method="post" class="row">
        <select name="engine" aria-label="{{ t('Reprocess') }}">
          <option value="">—</option>
          <option value="opencode">opencode</option>
          <option value="ollama">ollama</option>
          <option value="api">api</option>
        </select>
        <button type="submit">{{ t('Reprocess') }}</button>
      </form>
      <form action="/item/{{ note.id }}/delete" method="post">
        <button type="submit">{{ t('Delete') }}</button>
      </form>
    </div>
    <datalist id="known">
      {% for name in categories %}<option value="{{ name }}">{% endfor %}
    </datalist>
```

El CSS ya las deja invisibles hasta que pasás el mouse por la ficha
(`.actions { opacity: 0 }` y `.item:hover .actions`), que es el criterio visual
del spec: las acciones no compiten con el texto.

- [ ] **Step 8: Escribir las dos plantillas**

`src/oknowledge/web/templates/categories.html`:

```html
{% extends "base.html" %}
{% block main %}
  <h1>{{ t('Categories') }}</h1>
  <ul class="hits">
    {% for name, count in categories.items() %}
      <li>
        <form class="row" action="/categories/rename" method="post">
          <input type="hidden" name="old" value="{{ name }}">
          <span class="cat">{{ name }}</span> <span class="meta">{{ count }}</span>
          <span class="actions">
            <input name="new" list="known" placeholder="{{ t('Rename') }} / {{ t('Merge into') }}">
            <button type="submit">{{ t('Save') }}</button>
          </span>
        </form>
      </li>
    {% endfor %}
  </ul>
  <datalist id="known">
    {% for name in categories %}<option value="{{ name }}">{% endfor %}
  </datalist>
{% endblock %}
```

`src/oknowledge/web/templates/settings.html`:

```html
{% extends "base.html" %}
{% block main %}
  <h1>{{ t('Settings') }}</h1>
  <form action="/settings" method="post">
    <h2>{{ t('Engines') }}</h2>
    <p class="meta">El orden es la prioridad. Lo que no esté tildado, no se usa.</p>
    {% for name in ['opencode', 'ollama', 'api'] %}
      <p class="row">
        <label><input type="checkbox" name="chain" value="{{ name }}"
                      {% if name in cfg.chain %}checked{% endif %}> {{ name }}</label>
        <input name="{{ name }}_model" placeholder="model"
               value="{{ cfg.engines.get(name, {}).get('model', '') }}">
      </p>
    {% endfor %}
    <p class="meta">La API key no se escribe acá: va en <code>config.toml</code>
      como <code>key_env</code>, o en la variable de entorno que ese campo nombre.</p>

    <h2>{{ t('Summary language') }}</h2>
    <label><input type="radio" name="language" value="es"
                  {% if cfg.language == 'es' %}checked{% endif %}> Español</label>
    <label><input type="radio" name="language" value="en"
                  {% if cfg.language == 'en' %}checked{% endif %}> English</label>

    <h2>{{ t('Interface language') }}</h2>
    <label><input type="radio" name="ui_language" value="en"
                  {% if ui == 'en' %}checked{% endif %}> English</label>
    <label><input type="radio" name="ui_language" value="es"
                  {% if ui == 'es' %}checked{% endif %}> Español</label>

    <h2>{{ t('Keep by default') }}</h2>
    <label><input type="radio" name="default_content" value="full"
                  {% if cfg.default_content == 'full' %}checked{% endif %}> Full</label>
    <label><input type="radio" name="default_content" value="summary"
                  {% if cfg.default_content == 'summary' %}checked{% endif %}> Summary</label>

    <p><button type="submit" class="button">{{ t('Save') }}</button></p>
  </form>
{% endblock %}
```

Y agregar al CSS:

```css
.row { display: flex; align-items: center; gap: 0.6rem; padding: 0.9rem 0; }
.row .actions { margin-left: auto; display: flex; gap: 0.4rem; }
form h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em;
          color: var(--dim); margin-top: 2rem; }
form label { display: inline-flex; align-items: center; gap: 0.4rem; margin-right: 1.2rem; }
input[type=text], input:not([type]), button { padding: 0.4rem 0.7rem; font: inherit;
  border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: inherit; }
```

- [ ] **Step 9: Correr los tests**

Run: `pytest tests/test_vault_edit.py tests/test_web_write.py -v`
Expected: PASS, 15 tests

- [ ] **Step 10: Commit**

```bash
git add src/oknowledge tests/test_vault_edit.py tests/test_web_write.py pyproject.toml
git commit -m "feat: edit categories, tags and settings from the web"
```

---

### Task 14: `serve` — levantar la web cuando se la abre y apagarla sola

**Files:**
- Create: `src/oknowledge/web/runner.py`
- Modify: `src/oknowledge/cli.py`
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: `create_app` (Task 12), `Config` (Task 1).
- Produces: `runner.IdleTimer` (clase con `touch()`, `expired(now)`), `runner.serve(cfg, open_browser: bool) -> None`, y el subcomando `oknowledge serve`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_serve.py`:

```python
import pytest

from oknowledge.cli import main
from oknowledge.config import Config
from oknowledge.web.runner import IdleTimer


def test_a_fresh_timer_is_not_expired():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    assert timer.expired(1000.0) is False


def test_it_expires_after_the_idle_window():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    assert timer.expired(1899.0) is False
    assert timer.expired(1901.0) is True


def test_every_request_pushes_the_deadline_back():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.touch(1800.0)
    assert timer.expired(1901.0) is False
    assert timer.expired(2701.0) is True


def test_zero_seconds_means_never_shut_down():
    timer = IdleTimer(seconds=0, now=lambda: 1000.0)
    assert timer.expired(10_000_000.0) is False


def test_serve_passes_the_port_and_the_browser_flag(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, port=9123)
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: cfg)

    seen = {}
    monkeypatch.setattr("oknowledge.cli.serve",
                        lambda config, open_browser: seen.update(port=config.port,
                                                                 open=open_browser))
    main(["serve", "--open"])
    assert seen == {"port": 9123, "open": True}
```

- [ ] **Step 2: Correrlo y ver que falla**

Run: `pytest tests/test_serve.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.web.runner'`

- [ ] **Step 3: Escribir `web/runner.py`**

```python
"""Levantar la web a demanda y apagarla cuando nadie la mira.

No hay demonio: el servidor existe mientras lo estés usando.
"""

from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn

from ..config import Config
from .app import create_app


class IdleTimer:
    """Cuenta desde el último pedido. `seconds=0` significa no apagarse nunca."""

    def __init__(self, seconds: int, now=time.monotonic):
        self.seconds = seconds
        self._now = now
        self.last = now()

    def touch(self, when: float | None = None) -> None:
        self.last = self._now() if when is None else when

    def expired(self, when: float | None = None) -> bool:
        if self.seconds <= 0:
            return False
        moment = self._now() if when is None else when
        return (moment - self.last) > self.seconds


def serve(cfg: Config, open_browser: bool = False) -> None:
    app = create_app(cfg)
    timer = IdleTimer(cfg.idle_timeout)

    @app.middleware("http")
    async def keep_alive(request, call_next):
        timer.touch()
        return await call_next(request)

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=cfg.port, log_level="warning",
    ))

    def watchdog():
        # Un hilo común y no una tarea de asyncio: no necesita engancharse al
        # ciclo de vida de la app, que en FastAPI moderno ya no acepta on_event.
        while not server.should_exit:
            time.sleep(5)
            if timer.expired():
                server.should_exit = True

    threading.Thread(target=watchdog, daemon=True).start()

    if open_browser:
        threading.Timer(0.8, webbrowser.open, [f"http://127.0.0.1:{cfg.port}/"]).start()

    server.run()
```

- [ ] **Step 4: Agregar el subcomando a `cli.py`**

```python
from .web.runner import serve

    serve_cmd = subs.add_parser("serve", help="open the library in the browser")
    serve_cmd.add_argument("--open", action="store_true", help="also open the browser")

    # ... dentro de main(), junto a los otros comandos:
    if args.command == "serve":
        serve(cfg, open_browser=args.open)
        return 0
```

- [ ] **Step 5: Correr los tests**

Run: `pytest tests/test_serve.py -v`
Expected: PASS, 5 tests

- [ ] **Step 6: Probarla a mano**

```bash
~/.local/share/oknowledge/venv/bin/oknowledge serve --open
```

Mirar la biblioteca con las notas que guardaste en la Task 11: que la grilla se vea, que el buscador encuentre, que la ficha abra, y que a los 15 minutos sin tocarla el proceso termine solo.

- [ ] **Step 7: Commit**

```bash
git add src/oknowledge/web/runner.py src/oknowledge/cli.py tests/test_serve.py
git commit -m "feat: serve the library on demand and shut it down when idle"
```

---

### Task 15: El plugin de Omarchy

El plugin no sabe nada de HTML, de IA ni del vault: pega el link, llama al CLI y mira la carpeta de la cola.

**Referencia obligatoria antes de empezar:** `~/.config/omarchy/plugins/io.github.ferc10110.active-break/` es un plugin del mismo tipo (`service` + `bar-widget`) que ya funciona. De ahí se copian los idiomas de la casa — los `import` del kit (`qs.Ui`, `qs.Commons`), cómo `BarWidget.qml` obtiene su servicio con `bar.shell.serviceFor(moduleName)`, cómo inyecta el panel con un `Loader`, y cómo `I18n.js` expone `module.exports` guardado por `typeof module`. Este plan da la lógica propia de oknowledge; la forma de los archivos sale de ahí.

**Files:**
- Create: `plugin/manifest.json`
- Create: `plugin/I18n.js`
- Create: `plugin/Service.qml`
- Create: `plugin/BarWidget.qml`
- Create: `plugin/Panel.qml`
- Test: verificación en vivo (QML no tiene tests automáticos en este proyecto)

**Interfaces:**
- Consumes: el CLI de Tasks 11 y 14 (`oknowledge add --json`, `oknowledge status --json`, `oknowledge serve --open`), la carpeta de cola de Task 9, el archivo de idioma compartido.
- Produces: el plugin `io.github.ferc10110.oknowledge` con los comandos IPC `save`, `saveUrl <url>`, `open`, `status`, `retry`.

- [ ] **Step 1: Comprobar las herramientas que el plugin asume**

```bash
which wl-paste && wl-paste --no-newline | head -c 100; echo
ls ~/.local/share/oknowledge/venv/bin/oknowledge
```

Expected: `wl-paste` existe y devuelve el portapapeles; el CLI está instalado. Si `wl-paste` no estuviera, instalarlo con `omarchy pkg add wl-clipboard` antes de seguir.

- [ ] **Step 2: Escribir `plugin/manifest.json`**

```json
{
  "schemaVersion": 1,
  "id": "io.github.ferc10110.oknowledge",
  "name": "oknowledge",
  "version": "0.1.0",
  "author": "Fernando Cancro",
  "license": "MIT",
  "description": "Paste a link and get it summarized, categorized and tagged into your Obsidian vault.",
  "kinds": ["service", "bar-widget"],
  "entryPoints": {
    "service": "Service.qml",
    "barWidget": "BarWidget.qml"
  },
  "barWidget": {
    "displayName": "oknowledge",
    "description": "Save a link to your library",
    "category": "Productivity",
    "aliases": ["links", "bookmarks", "obsidian", "knowledge"],
    "allowMultiple": false,
    "defaultSection": "left"
  }
}
```

- [ ] **Step 3: Escribir `plugin/I18n.js`**

```js
// El texto en inglés es la clave. Si falta una traducción, sale el inglés y
// nada se rompe. La preferencia la lee Service.qml del archivo compartido.

var STRINGS = {
  es: {
    "Paste a link": "Pegar un link",
    "Nothing in the clipboard": "No hay nada en el portapapeles",
    "That is not a link": "Eso no es un link",
    "Full": "Completo",
    "Summary": "Sólo resumen",
    "Saving…": "Guardando…",
    "Saved": "Guardado",
    "Incomplete": "Incompleto",
    "Retry": "Reintentar",
    "Open library": "Abrir la biblioteca",
    "%1 in progress": "%1 en curso",
    "Recent": "Recientes",
    "Nothing saved yet": "Todavía no guardaste nada"
  }
}

function t(text, lang, args) {
  var table = STRINGS[lang]
  var out = (table && Object.prototype.hasOwnProperty.call(table, text)) ? table[text] : text
  return out.replace(/%(\d+)/g, function (match, digits) {
    var n = Number(digits)
    if (n === 0 || !args || n > args.length) return match
    return String(args[n - 1])
  })
}

if (typeof module !== "undefined") {
  module.exports = { t: t, STRINGS: STRINGS }
}
```

- [ ] **Step 4: Escribir `plugin/Service.qml`**

```qml
// El estado del plugin: el idioma, la cola y la forma de llamar al CLI.
// Una sola instancia: el widget existe una vez por monitor, esto no.

import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io

Item {
  id: service

  readonly property string cli: Quickshell.env("HOME") + "/.local/share/oknowledge/venv/bin/oknowledge"
  readonly property string queueDir: Quickshell.env("HOME") + "/.local/state/oknowledge/queue"

  property string language: "en"
  property string defaultContent: "full"
  property int working: 0
  property var recent: []
  property string lastError: ""

  function t(text, args) { return I18n.t(text, service.language, args) }

  // ---- idioma compartido con los demás plugins
  FileView {
    id: languageFile
    path: Quickshell.env("HOME") + "/.config/omarchy/plugin-language.json"
    watchChanges: true
    printErrors: false
    blockLoading: true
    onLoaded: {
      try {
        var value = JSON.parse(text()).language
        service.language = (value === "es" || value === "en") ? value : "en"
      } catch (e) {
        service.language = "en"
      }
    }
    onLoadFailed: service.language = "en"
  }

  // ---- la cola, que son archivos: por eso el widget la puede mirar
  FolderListModel {
    id: queue
    folder: "file://" + service.queueDir
    nameFilters: ["*.json"]
    showDirs: false
    onCountChanged: statusProc.running = true
  }

  Timer {
    id: poll
    interval: 1500
    repeat: true
    running: service.working > 0
    onTriggered: statusProc.running = true
  }

  Process {
    id: statusProc
    command: [service.cli, "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var entries = JSON.parse(text)
        } catch (e) {
          return
        }
        var pending = 0
        for (var i = 0; i < entries.length; i++)
          if (entries[i].status === "pending") pending++
        service.working = pending
        service.recent = entries.slice(0, 5)
      }
    }
  }

  // ---- guardar un link
  property string pendingUrl: ""

  function looksLikeUrl(text) {
    return /^https?:\/\/\S+$/i.test(String(text).trim())
  }

  function saveUrl(url, mode) {
    if (!looksLikeUrl(url)) {
      service.lastError = service.t("That is not a link")
      return false
    }
    service.working += 1
    addProc.command = [service.cli, "add", String(url).trim(),
                       mode === "summary" ? "--summary" : "--full", "--json"]
    addProc.running = true
    return true
  }

  Process {
    id: addProc
    stdout: StdioCollector { waitForEnd: true }
    onExited: {
      service.working = Math.max(0, service.working - 1)
      statusProc.running = true
    }
  }

  // ---- el portapapeles, para el atajo y para el panel
  Process {
    id: clipProc
    command: ["wl-paste", "--no-newline"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        service.pendingUrl = String(text).trim()
        if (service.autoSave) {
          service.autoSave = false
          service.saveUrl(service.pendingUrl, service.defaultContent)
        }
      }
    }
  }

  property bool autoSave: false

  function readClipboard() { clipProc.running = true }
  function saveClipboard() { service.autoSave = true; clipProc.running = true }

  function openLibrary() {
    Quickshell.execDetached([service.cli, "serve", "--open"])
  }

  function retryAll() {
    Quickshell.execDetached([service.cli, "retry"])
  }

  IpcHandler {
    target: "io.github.ferc10110.oknowledge"

    function save(): string { service.saveClipboard(); return "ok" }
    function saveUrl(url: string): string { return service.saveUrl(url, service.defaultContent) ? "ok" : "not a url" }
    function open(): string { service.openLibrary(); return "ok" }
    function retry(): string { service.retryAll(); return "ok" }
    function status(): string { return JSON.stringify({ working: service.working, recent: service.recent }) }
  }

  Component.onCompleted: statusProc.running = true
}
```

- [ ] **Step 5: Escribir `plugin/BarWidget.qml` y `plugin/Panel.qml`**

`BarWidget.qml` — copiar de `active-break/BarWidget.qml` los `import`, la obtención del servicio y el `Loader` del panel, y reemplazar la cara por esta:

- Ícono: `󰓹` (nf-md-bookmark_multiple) en color normal.
- Cuando `service.working > 0`: el mismo ícono más el número, en color `accent`.
- Clic izquierdo: abre y cierra el panel.
- Clic medio: `service.saveClipboard()` — guarda lo que haya en el portapapeles sin abrir nada.
- Clic derecho: `service.openLibrary()`.
- Tooltip: `service.t("%1 in progress", [service.working])` cuando hay trabajo; si no, el título del último guardado.

`Panel.qml` — copiar de `active-break/Panel.qml` la estructura (`Panel` + `KeyboardPanel` + `PanelKeyCatcher`) y poner adentro:

1. Al abrirse (`onVisibleChanged` cuando pasa a visible) llamar a `service.readClipboard()`.
2. Un bloque arriba con `service.pendingUrl`:
   - si está vacío → el texto `service.t("Nothing in the clipboard")`;
   - si no parece URL → `service.t("That is not a link")`;
   - si parece URL → la URL recortada a una línea, y dos botones: **Full** y **Summary**, que llaman a `service.saveUrl(service.pendingUrl, "full" | "summary")` y cierran el panel.
3. Debajo, `service.t("Recent")` y la lista de `service.recent`: título (o la URL si no hay título), el estado, y para los que no están en `ok` un botón `service.t("Retry")` que llama a `service.retryAll()`.
4. Abajo, un botón `service.t("Open library")` que llama a `service.openLibrary()`.

Todos los textos pasan por `service.t(...)`, nunca literales, para que el idioma cambie en vivo.

- [ ] **Step 6: Instalar y validar**

```bash
ln -s /home/fer/Projects/oknowledge/plugin ~/.config/omarchy/plugins/io.github.ferc10110.oknowledge
omarchy plugin validate /home/fer/Projects/oknowledge/plugin
omarchy-shell lock isLocked     # tiene que decir false antes de reiniciar
omarchy restart shell
omarchy plugin enable io.github.ferc10110.oknowledge
```

Expected: `validate` sin errores, el widget aparece en la barra, y el log de la shell sin warnings de QML.

- [ ] **Step 7: Probarlo**

```bash
wl-copy https://omarchy.org/
omarchy-shell io.github.ferc10110.oknowledge save
omarchy-shell io.github.ferc10110.oknowledge status
```

Expected: el contador sube, baja, y aparece una nota nueva en el vault.

- [ ] **Step 8: Atajos de teclado**

En `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + ALT + K", "oknowledge: save the clipboard", "omarchy-shell io.github.ferc10110.oknowledge save")
o.bind("SUPER + ALT + SHIFT + K", "oknowledge: open the library", "omarchy-shell io.github.ferc10110.oknowledge open")
```

Verificar con `hyprctl reload && hyprctl configerrors`.

- [ ] **Step 9: Commit**

```bash
git add plugin
git commit -m "feat: the omarchy plugin: paste a link from the bar"
```

---

### Task 16: README y verificación de punta a punta

**Files:**
- Create: `README.md`
- Create: `preview.png`
- Test: la lista de verificación del spec, corrida entera

**Interfaces:**
- Consumes: todo.
- Produces: nada que use otra tarea.

- [ ] **Step 1: Escribir el README**

En inglés, con estas secciones, siguiendo el estilo de los otros plugins del usuario: **What it does**, **Install** (el venv, el `config.toml`, el symlink del plugin, `omarchy plugin enable`), **Use** (la barra, los atajos, los subcomandos del CLI), **The vault** (la forma de una nota, el índice, que editar a mano es parte del diseño y que una nota sin el marcador no se toca), **Engines** (la cadena, los tres motores, dónde va la API key, que ollama es el único que no sale de la máquina), **The two languages** (interfaz vs. contenido), **Files**, **Remove**, **Development** (`pytest`, la estructura de `src/`), **License**.

- [ ] **Step 2: Correr la batería completa**

Run: `pytest -v`
Expected: PASS, sin warnings.

- [ ] **Step 3: La verificación en vivo del spec, los nueve puntos**

1. `omarchy plugin validate /home/fer/Projects/oknowledge/plugin` limpio y sin warnings QML en el log.
2. Guardar y revisar la nota de: un artículo, un video de YouTube con transcripción, un PDF y un repositorio de GitHub.
3. Con la red cortada (`nmcli networking off`), guardar un link: la nota tiene que quedar `partial`; volver la red y correr `oknowledge retry` tiene que completarla.
4. Guardar el mismo link dos veces: una sola nota.
5. Cambiar `category` a mano en Obsidian y correr `oknowledge reindex`: la nota cambia de índice.
6. Fusionar dos categorías desde la web y confirmar que las notas y los índices quedan consistentes.
7. Cambiar la cadena a `["ollama"]` (bajando antes un modelo con `ollama pull qwen2.5:7b`) y repetir el punto 2.
8. Con la interfaz en inglés y `[ai] language = "es"`, guardar un artículo en inglés: la interfaz sigue en inglés y el resumen sale en español.
9. Escribir `{"language": "es"}` en `~/.config/omarchy/plugin-language.json`: el panel y la web pasan a español, y los resúmenes ya guardados no cambian.

Anotar en el commit cualquier punto que no pase, y arreglarlo antes de cerrar.

- [ ] **Step 4: La captura**

Con la biblioteca ya con varias notas reales, sacar `preview.png` de la web (`grim` y recortar con `magick`), para el README.

- [ ] **Step 5: Commit**

```bash
git add README.md preview.png
git commit -m "docs: readme and preview"
```
