# Importador de WhatsApp — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar los 1215 links de un export de WhatsApp como notas `partial`
fechadas cuando se mandaron, en segundos, y poder analizarlas después de a tandas.

**Architecture:** Un parser puro (texto → lista, sin disco ni red) en un módulo
nuevo; una función de escritura en bloque en `pipeline.py` que paga los pasos
caros —el escaneo del vault y la reconstrucción de índices— una vez para el
lote en lugar de una vez por link; y dos cambios chicos en el CLI.

**Tech Stack:** Python 3.14, stdlib sola para el parser (`re`, `datetime`,
`dataclasses`). pytest. Sin dependencias nuevas.

**Spec:** `docs/2026-10-05-importar-whatsapp-design.md`

## Global Constraints

- **Nunca `datetime.utcnow()` ni `utcfromtimestamp()`.** Usar
  `datetime.datetime.now(datetime.timezone.utc)` y
  `datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)`.
- **Ningún commit lleva líneas de atribución** a Claude: ni `Co-Authored-By`,
  ni `Claude-Session`, ni "Generated with Claude Code". Los repos son públicos.
- **Ningún test toca la red ni corre un programa.** `tests/conftest.py` lo
  prohíbe con `pytest.fail`, que es un `BaseException` y por lo tanto no lo
  tapa ningún `except Exception` del código bajo prueba.
- **La suite corre con `-W error`** y la salida tiene que quedar limpia.
- **El sistema sólo escribe dentro de `<vault>/oknowledge/`** y sólo en
  archivos con `oknowledge: 1` en el frontmatter. Todo write pasa por
  `vault.write_note()`, que pasa por `ensure_inside_root`.
- **Nunca se pierde un link.** Un link capturado que no se pudo guardar se
  reporta; no desaparece en silencio.
- **El CLI habla inglés.** No se agregan strings a `i18n.py` para esto: el
  idioma de la interfaz web y el de la IA son otra cosa.
- **Códigos de salida:** `0` funcionó · `1` corrió pero algo quedó sin
  terminar · `2` la entrada o la configuración están mal · `3` inesperado.
- **Entorno:** venv en `~/.local/share/oknowledge/venv`. Los tests se corren
  con `~/.local/share/oknowledge/venv/bin/python -m pytest` desde la raíz del
  repo. Rama `feat/v1`, que ya existe y no está mergeada.

## Review Focus

Cinco clases de entrada que el spec implica y que un parser escrito sólo
contra el ejemplo de 13 líneas no vería. Cada una tiene su test en la tarea
que es dueña del código.

1. **Marcas invisibles alrededor del timestamp.** WhatsApp intercala `U+200E`
   (LRM) y espacios duros (`U+00A0`, `U+202F`) en los exports reales. Un regex
   escrito contra texto limpio encuentra **cero** mensajes en el archivo de
   verdad, que es el peor modo de falla posible: silencioso y total. → Tarea 1.
2. **URLs con paréntesis balanceados.** `https://es.wikipedia.org/wiki/Python_(lenguaje)`
   es un link real y frecuente; un recortador de puntuación ingenuo lo parte y
   guarda un link roto. → Tarea 2.
3. **CRLF y BOM.** El archivo sale de Android y puede pasar por Windows o por
   Drive. Un `\r` al final de cada línea o un BOM al principio también dan cero
   mensajes. → Tarea 1.
4. **Bytes que no son UTF-8 válido.** Un export de seis años puede traer uno.
   Leerlo con `encoding="utf-8"` estricto aborta la importación entera por un
   byte; hay que leerlo tolerante y seguir. → Tarea 5.
5. **Dos links en un mensaje, separados por puntuación.** `foo.com, bar.org/x`
   tiene que dar dos links, no uno ni ninguno, y el comentario tiene que
   quedar sin los dos. → Tarea 2.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/oknowledge/whatsapp.py` | **Nuevo.** El parser, puro. Dos capas: mensajes (timestamp, remitente, texto) y links (qué cuenta como link). No importa nada de `pipeline`, `vault` ni `config`: se puede probar con un string. |
| `tests/test_whatsapp.py` | **Nuevo.** El parser, con strings. |
| `src/oknowledge/pipeline.py` | **Modificar.** Agregar `ImportResult` e `import_links()`. Arreglar `saved=_today()` en los dos lugares. Agregar `limit` a `retry()`. |
| `tests/test_import.py` | **Nuevo.** La escritura en bloque, con un vault en `tmp_path`. |
| `tests/test_pipeline.py` | **Modificar.** Los tests del arreglo de la fecha y de `retry(limit=...)`. |
| `src/oknowledge/cli.py` | **Modificar.** El subcomando `import` con `--dry-run` y `--json`; `--limit` en `retry`. |
| `tests/test_cli.py` | **Modificar.** Los dos comandos. |
| `README.md` | **Modificar.** La tabla de comandos. |

El parser va en su propio módulo y no en `pipeline.py` por una razón concreta:
`pipeline.py` ya tiene 700 líneas y conoce la red, el vault y la cola. El
parser no conoce nada de eso y no tiene por qué heredarlo para ser probado.

---

## Tarea 1: La capa de mensajes del parser

**Files:**
- Create: `src/oknowledge/whatsapp.py`
- Test: `tests/test_whatsapp.py`

**Interfaces:**
- Consumes: nada. Es el primer módulo.
- Produces:
  - `class BadExport(Exception)`
  - `@dataclass Message` con `sent: str` (YYYY-MM-DD), `sender: str`, `text: str`
  - `def messages(text: str) -> tuple[list[Message], bool, bool]` →
    `(mensajes, day_first, assumed)`. Levanta `BadExport` si ninguna línea
    tiene el formato, o si el orden de fecha es inconsistente.

- [ ] **Step 1: Write the failing test**

En `tests/test_whatsapp.py`:

```python
"""El parser del export de WhatsApp. Sin disco, sin red: texto a lista.

Casi todo acá es sobre lo que el archivo real trae y el ejemplo limpio no:
marcas invisibles, saltos de línea de Windows, mensajes partidos. Un regex
escrito contra texto prolijo encuentra cero mensajes en el archivo de verdad.
"""

import pytest

from oknowledge.whatsapp import BadExport, messages

REAL = """\
18/7/2019, 11:36 - Fer: https://scratux.org/#download
23/7/2019, 11:39 - Fer: sudo chkrootkit
21/7/2019, 13:50 - Fer: “Easy DevOps” by George Seif https://link.medium.com/JfoglQ1zvY
"""


def test_the_real_export_lines_are_read():
    found, day_first, assumed = messages(REAL)

    assert [(m.sent, m.sender) for m in found] == [
        ("2019-07-18", "Fer"), ("2019-07-23", "Fer"), ("2019-07-21", "Fer")]
    assert found[1].text == "sudo chkrootkit"
    assert (day_first, assumed) == (True, False)


def test_a_two_digit_year_is_this_century():
    found, _, _ = messages("14/3/25, 21:07 - Fer: hola\n")

    assert found[0].sent == "2025-03-14"


def test_a_message_split_over_lines_stays_one_message():
    """Un link partido en dos líneas no se parte."""
    found, _, _ = messages(
        "18/7/2019, 11:36 - Fer: mirá esto\nsegunda línea\n"
        "19/7/2019, 09:00 - Fer: otro\n")

    assert len(found) == 2
    assert found[0].text == "mirá esto\nsegunda línea"


def test_a_system_line_has_no_sender_and_is_still_read():
    """Un link dentro de un aviso del sistema sigue siendo un link."""
    found, _, _ = messages("18/7/2019, 11:36 - Fer creó el grupo\n")

    assert found[0].sender == ""
    assert found[0].text == "Fer creó el grupo"


def test_the_invisible_marks_whatsapp_puts_in_do_not_hide_every_message():
    """U+200E y los espacios duros son lo que trae el archivo real.

    Sin limpiarlos, el regex da cero mensajes: silencioso y total.
    """
    found, _, _ = messages(
        "‎18/7/2019, 11:36 - Fer: https://e.com/x\n")

    assert len(found) == 1
    assert found[0].sent == "2019-07-18"


def test_windows_line_endings_and_a_bom_are_read():
    found, _, _ = messages("﻿18/7/2019, 11:36 - Fer: hola\r\n")

    assert len(found) == 1
    assert found[0].text == "hola"


def test_day_first_is_detected_from_a_day_over_twelve():
    _, day_first, assumed = messages("18/7/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (True, False)


def test_month_first_is_detected_from_a_second_field_over_twelve():
    found, day_first, assumed = messages("7/18/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (False, False)
    assert found[0].sent == "2019-07-18"


def test_an_ambiguous_file_assumes_day_first_and_says_so():
    """Un export de menos de 13 días no tiene evidencia. Se asume y se avisa."""
    _, day_first, assumed = messages("7/8/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (True, True)


def test_a_file_that_contradicts_itself_is_refused():
    with pytest.raises(BadExport) as raised:
        messages("18/7/2019, 11:36 - Fer: x\n7/18/2019, 11:36 - Fer: y\n")

    assert "18/7/2019" in str(raised.value)
    assert "7/18/2019" in str(raised.value)


def test_a_file_with_no_recognisable_line_names_the_format_it_wanted():
    with pytest.raises(BadExport) as raised:
        messages("esto no es un export\nni esto tampoco\n")

    assert "D/M/YYYY" in str(raised.value)
    assert "esto no es un export" in str(raised.value)


def test_an_empty_file_is_refused_too():
    with pytest.raises(BadExport):
        messages("")


def test_an_impossible_date_is_skipped_not_fatal():
    """31/2 no existe. Una línea mala no se lleva el archivo."""
    found, _, _ = messages("31/2/2019, 11:36 - Fer: x\n18/7/2019, 11:36 - Fer: y\n")

    assert [m.text for m in found] == ["y"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_whatsapp.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'oknowledge.whatsapp'`

- [ ] **Step 3: Write minimal implementation**

Crear `src/oknowledge/whatsapp.py`:

```python
"""Leer un export de chat de WhatsApp.

Puro: texto adentro, listas afuera. No conoce el vault, la cola ni la red,
así que se prueba con un string y sin montar nada.

Dos capas. Esta de acá convierte el archivo en mensajes; la de abajo decide
qué pedazo de un mensaje es un link. Están separadas porque fallan por
razones distintas: el formato de la línea es cosa de WhatsApp, y qué cuenta
como link es cosa de cómo escribe el usuario.
"""

import datetime as dt
import re
from dataclasses import dataclass

# Lo que WhatsApp intercala en un export real y no se ve al abrirlo: marcas
# de dirección y espacios que no son el espacio. Sin sacarlos, el regex de
# abajo no matchea una sola línea del archivo de verdad.
INVISIBLE = str.maketrans({
    "‎": "", "‏": "", "‪": "", "‫": "", "‬": "",
    "﻿": "", " ": " ", " ": " ", " ": " ",
})

LINE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s+-\s+(.*)$"
)

WANTED = "D/M/YYYY, HH:MM - Remitente: mensaje"


class BadExport(Exception):
    """El archivo no es un export que se pueda leer."""


@dataclass
class Message:
    sent: str        # YYYY-MM-DD
    sender: str      # "" en un aviso del sistema
    text: str


def _clean(text: str) -> list[str]:
    return text.translate(INVISIBLE).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _order(stamps: list[tuple[int, int]], raw: list[str]) -> tuple[bool, bool]:
    """(día primero, se asumió). Evidencia antes que convención."""
    day_first = [i for i, (a, _) in enumerate(stamps) if a > 12]
    month_first = [i for i, (_, b) in enumerate(stamps) if b > 12]
    if day_first and month_first:
        raise BadExport(
            f"the dates contradict each other: {raw[day_first[0]]!r} reads as "
            f"day/month and {raw[month_first[0]]!r} reads as month/day"
        )
    if day_first:
        return True, False
    if month_first:
        return False, False
    return True, True        # sin evidencia: día primero, y se avisa


def messages(text: str) -> tuple[list[Message], bool, bool]:
    """(los mensajes, día primero, se asumió el orden).

    Una línea que no tiene el formato es continuación del mensaje anterior,
    así que un mensaje de varias líneas no se parte. Una línea con el formato
    pero con una fecha imposible se saltea: una línea mala no se lleva el
    archivo, que es la regla de que no se pierde un link aplicada al parser.
    """
    lines = _clean(text)
    starts = [n for n, line in enumerate(lines) if LINE.match(line) is not None]
    if not starts:
        first = next((line for line in lines if line.strip()), "")
        raise BadExport(
            f"no line looks like a WhatsApp export; expected {WANTED!r}, "
            f"and the file starts with {first!r}"
        )

    stamps: list[tuple[int, int]] = []
    bodies: list[tuple[re.Match, str]] = []
    for n, start in enumerate(starts):
        found = LINE.match(lines[start])
        assert found is not None          # starts sólo tiene líneas que matchean
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        tail = lines[start + 1:end]
        while tail and not tail[-1].strip():
            tail.pop()                    # el salto de línea final del archivo
        stamps.append((int(found.group(1)), int(found.group(2))))
        bodies.append((found, "\n".join([found.group(7), *tail])))

    day_first, assumed = _order(stamps, [lines[n] for n in starts])

    out: list[Message] = []
    for (found, body), (first, second) in zip(bodies, stamps):
        day, month = (first, second) if day_first else (second, first)
        year = int(found.group(3))
        year += 2000 if year < 100 else 0
        try:
            sent = dt.date(year, month, day).isoformat()
        except ValueError:
            continue                      # 31/2: una línea mala, no un archivo malo
        sender, _, rest = body.partition(": ")
        if not rest and ": " not in body:
            sender, rest = "", body       # un aviso del sistema no tiene remitente
        out.append(Message(sent=sent, sender=sender, text=rest))
    return out, day_first, assumed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_whatsapp.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Run the whole suite**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q`
Expected: todo pasa. El módulo es nuevo y nada lo importa todavía.

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/whatsapp.py tests/test_whatsapp.py
git commit -m "feat: read the messages out of a WhatsApp export"
```

---

## Tarea 2: La capa de links del parser

**Files:**
- Modify: `src/oknowledge/whatsapp.py`
- Test: `tests/test_whatsapp.py`

**Interfaces:**
- Consumes: de la Tarea 1 — `messages(text) -> (list[Message], bool, bool)`,
  `Message(sent, sender, text)`, `BadExport`.
- Produces:
  - `TLDS: frozenset[str]`, `EXTENSIONS: frozenset[str]`
  - `def find_links(text: str) -> list[tuple[str, bool]]` → `[(url, bare)]`
  - `@dataclass Imported` con `url: str`, `sent: str`, `comment: str`,
    `sender: str`, `raw: str`, `bare: bool`
  - `@dataclass Scan` con `links: list[Imported]`, `suspicious: list[str]`,
    `messages: int`, `day_first: bool`, `assumed: bool`
  - `def parse(text: str) -> Scan`

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_whatsapp.py`:

```python
from oknowledge.whatsapp import Scan, find_links, parse


@pytest.mark.parametrize("text,expected", [
    # completos
    ("https://scratux.org/#download", [("https://scratux.org/#download", False)]),
    ("http://viejo.example.com/x", [("http://viejo.example.com/x", False)]),
    # sueltos que cuentan
    ("youtu.be/abc", [("https://youtu.be/abc", True)]),
    ("scratux.org", [("https://scratux.org", True)]),
    ("www.foo.com", [("https://www.foo.com", True)]),
    ("example.py/docs", [("https://example.py/docs", True)]),
    # sueltos que no
    ("script.py", []),
    ("README.md", []),
    ("config.json", []),
    ("version 3.10", []),
    ("fer@gmail.com", []),
    ("sudo chkrootkit", []),
    ("11 5555-5555", []),
])
def test_what_counts_as_a_link(text, expected):
    assert find_links(text) == expected


def test_a_url_with_balanced_parens_is_not_cut():
    """Wikipedia pone paréntesis en la URL y son parte del link."""
    url = "https://es.wikipedia.org/wiki/Python_(lenguaje)"

    assert find_links(f"mirá {url}") == [(url, False)]


def test_a_url_inside_parens_loses_only_the_closing_one():
    assert find_links("(https://e.com/x)") == [("https://e.com/x", False)]


@pytest.mark.parametrize("text,url", [
    ("mirá github.com/y.", "https://github.com/y"),
    ("“e.com/z”", "https://e.com/z"),
    ("e.com/w, y nada más", "https://e.com/w"),
    ("https://e.com/v!", "https://e.com/v"),
])
def test_punctuation_stuck_to_the_end_is_not_part_of_the_link(text, url):
    assert find_links(text) == [(url, url.count("://") == 1 and "://" not in text)]


def test_two_links_in_one_message_are_both_found():
    assert find_links("foo.com, bar.org/x") == [
        ("https://foo.com", True), ("https://bar.org/x", True)]


def test_a_bare_domain_inside_a_full_url_is_not_counted_twice():
    assert find_links("https://github.com/a/b") == [("https://github.com/a/b", False)]


def test_the_comment_is_the_message_without_the_links():
    scan = parse('21/7/2019, 13:50 - Fer: “Easy DevOps” by George Seif '
                 'https://link.medium.com/JfoglQ1zvY\n')

    assert scan.links[0].comment == "“Easy DevOps” by George Seif"
    assert scan.links[0].url == "https://link.medium.com/JfoglQ1zvY"
    assert scan.links[0].sent == "2019-07-21"
    assert scan.links[0].sender == "Fer"
    assert scan.links[0].bare is False


def test_a_message_that_is_only_a_link_has_no_comment():
    scan = parse("18/7/2019, 11:36 - Fer: https://e.com/x\n")

    assert scan.links[0].comment == ""


def test_the_raw_link_is_kept_for_the_dry_run():
    scan = parse("18/7/2019, 11:36 - Fer: mirá youtu.be/abc\n")

    assert scan.links[0].raw == "youtu.be/abc"
    assert scan.links[0].url == "https://youtu.be/abc"
    assert scan.links[0].bare is True


def test_a_message_with_no_link_is_not_imported():
    scan = parse("23/7/2019, 11:39 - Fer: sudo chkrootkit\n")

    assert scan.links == []
    assert scan.messages == 1


def test_a_message_that_looks_like_it_had_a_link_is_reported():
    """La lista que delata un link perdido, en vez de perderlo callado."""
    scan = parse("23/7/2019, 11:39 - Fer: mirá el config.json que te mandé\n")

    assert scan.links == []
    assert scan.suspicious == ["mirá el config.json que te mandé"]


def test_plain_text_with_no_dots_is_not_suspicious():
    scan = parse("23/7/2019, 11:39 - Fer: sudo chkrootkit\n")

    assert scan.suspicious == []


def test_the_scan_carries_the_date_order_through():
    scan = parse("7/8/2019, 11:36 - Fer: e.com\n")

    assert (scan.day_first, scan.assumed) == (True, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_whatsapp.py -q`
Expected: FAIL con `ImportError: cannot import name 'find_links'`

- [ ] **Step 3: Write minimal implementation**

Agregar a `src/oknowledge/whatsapp.py`:

```python
# Los TLDs que este archivo puede encontrar. Curada, no exhaustiva: una lista
# completa mete miles de sufijos de tres letras que convierten cualquier
# palabra con punto en un link. Se afina mirando la salida de --dry-run.
TLDS = frozenset("""
com org net io dev app me tv co info biz xyz online site tech blog news edu
gov mil ar es mx cl uy pe br us uk de fr it nl pt ru jp cn in au ca ch se no
fi dk pl cz gr tr il za kr be at ie nz eu gg to ly am st fm cc tk link page
cloud space live work wiki art design studio club shop store
""".split())

# TLDs reales que además son extensiones de archivo que este usuario escribe.
# Sin path gana la extensión; con path gana el dominio. `zip` y `mov` están
# porque Google los vendió como TLD y la colisión es peor que las otras.
EXTENSIONS = frozenset("sh py md ts js rs go pl so rb cs ai zip mov".split())

FULL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
# No precedido por @ (un mail), ni por otro carácter de dominio (para no
# cortar un host por la mitad). El path es opcional.
BARE = re.compile(
    r"(?<![\w@.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24}))"
    r"(/[^\s<>\"]*)?",
    re.IGNORECASE,
)
# Un punto entre letras: un mensaje así pudo tener un link que no matcheó.
MAYBE = re.compile(r"[a-z0-9]\.[a-z]{2,}", re.IGNORECASE)

TRAILING = ".,;:!?'\"”’»)]}>"


def _trim(url: str) -> str:
    """Saca la puntuación pegada al final sin romper un link que la usa.

    Un `)` se va sólo si no cierra un `(` del propio link: Wikipedia escribe
    `/wiki/Python_(lenguaje)` y ese paréntesis es parte de la URL.
    """
    while url and url[-1] in TRAILING:
        if url[-1] == ")" and url.count("(") > url.count(")") - 1:
            break
        url = url[:-1]
    return url


def find_links(text: str) -> list[tuple[str, bool]]:
    """[(url con esquema, venía sin esquema)], en el orden en que aparecen."""
    out: list[tuple[int, str, bool]] = []
    taken: list[tuple[int, int]] = []

    for found in FULL.finditer(text):
        url = _trim(found.group(0))
        if url:
            out.append((found.start(), url, False))
            taken.append((found.start(), found.start() + len(url)))

    for found in BARE.finditer(text):
        start = found.start()
        if any(a <= start < b for a, b in taken):
            continue                      # ya es parte de una URL completa
        tld = found.group(2).lower()
        if tld not in TLDS:
            continue
        path = found.group(3) or ""
        if tld in EXTENSIONS and not path:
            continue                      # script.py gana como extensión
        url = _trim(found.group(1) + path)
        if url:
            out.append((start, f"https://{url}", True))

    out.sort(key=lambda row: row[0])
    return [(url, bare) for _, url, bare in out]


@dataclass
class Imported:
    url: str          # con esquema, lista para normalize()
    sent: str         # YYYY-MM-DD
    comment: str      # el mensaje sin los links, o ""
    sender: str
    raw: str          # el link tal como estaba escrito
    bare: bool


@dataclass
class Scan:
    links: list[Imported]
    suspicious: list[str]
    messages: int
    day_first: bool
    assumed: bool


def _raw_of(text: str, url: str, bare: bool) -> str:
    """Lo que estaba escrito, para que el --dry-run muestre el original."""
    written = url[len("https://"):] if bare else url
    return written if written in text else url


def parse(text: str) -> Scan:
    """Un export entero a links fechados. Levanta BadExport si no se puede leer."""
    found, day_first, assumed = messages(text)
    links: list[Imported] = []
    suspicious: list[str] = []
    for message in found:
        urls = find_links(message.text)
        if not urls:
            if MAYBE.search(message.text):
                suspicious.append(message.text)
            continue
        comment = message.text
        for url, bare in urls:
            comment = comment.replace(_raw_of(message.text, url, bare), " ")
        comment = " ".join(comment.split())
        for url, bare in urls:
            links.append(Imported(url=url, sent=message.sent, comment=comment,
                                  sender=message.sender,
                                  raw=_raw_of(message.text, url, bare), bare=bare))
    return Scan(links=links, suspicious=suspicious, messages=len(found),
                day_first=day_first, assumed=assumed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_whatsapp.py -q`
Expected: PASS.

El test `test_punctuation_stuck_to_the_end_is_not_part_of_the_link` tiene una
expresión enrevesada para el flag `bare`. Si molesta, cambiarlo por cuatro
casos explícitos con el booleano escrito a mano — vale más claro que corto.

- [ ] **Step 5: Mutation-test the two clauses of the bare-domain rule**

Las dos cláusulas son el corazón de la tarea y un test que pasa sin ellas no
sirve. Guardar el archivo, aplicar cada mutante, confirmar que **se aplicó**,
correr, restaurar:

| Mutante | Qué cambia | Tiene que morir en |
|---|---|---|
| m1 | `if tld not in TLDS: continue` → borrado | `config.json`, `version 3.10` |
| m2 | `if tld in EXTENSIONS and not path` → `if False` | `script.py`, `README.md` |
| m3 | `and not path` → borrado | `example.py/docs` |
| m4 | `_trim` devuelve `url` sin tocar | la tabla de puntuación |
| m5 | el `break` del paréntesis → borrado | el caso de Wikipedia |
| m6 | el lookbehind `(?<![\w@.-])` → `(?<!@)` | `fer@gmail.com` sigue muerto, pero probar igual |

Si alguno **sobrevive**, el test que debía matarlo es ciego: arreglar el test,
no el mutante.

- [ ] **Step 6: Run the whole suite and commit**

```bash
~/.local/share/oknowledge/venv/bin/python -m pytest -q
git add src/oknowledge/whatsapp.py tests/test_whatsapp.py
git commit -m "feat: find the links in a WhatsApp message"
```

---

## Tarea 3: Conservar la fecha de una nota que ya existe

**Files:**
- Modify: `src/oknowledge/pipeline.py` (las dos líneas `saved=_today()`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: nada de las tareas anteriores. Es independiente y se puede hacer
  primera si conviene.
- Produces: `_partial_note(cfg, link, url, content, page, saved=None)` y el
  `Note(...)` de `_process` fechados con la nota que ya está en disco.

Esta tarea es un arreglo que vale por sí solo: una nota se guardó cuando se
guardó, y reanalizarla no la vuelve a guardar. La importación lo expone, pero
el bug existe hoy.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_pipeline.py`, al final:

```python
# --- la fecha de guardado es de cuando se guardó, no de cuando se reanalizó --


def test_a_reprocessed_note_keeps_the_day_it_was_saved(cfg, q, monkeypatch):
    """Reanalizar no es volver a guardar.

    Sin esto, importar seis años de links y después analizarlos los apila
    todos en el día del análisis.
    """
    extraction(monkeypatch, Unreadable("503"))
    no_pictures(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    path = next(cfg.links_dir.glob("*.md"))
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"saved: {TODAY}", "saved: 2019-07-18"), encoding="utf-8")

    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER]
    again = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert again.status == "ok"
    assert read_note(again.path).saved == "2019-07-18"
    assert first.id == again.id


def test_a_partial_note_rewritten_over_a_partial_one_keeps_its_date(cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("503"))
    no_pictures(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    path = next(cfg.links_dir.glob("*.md"))
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"saved: {TODAY}", "saved: 2019-07-18"), encoding="utf-8")

    extraction(monkeypatch, Unreadable("still 503"))
    again = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert read_note(again.path).saved == "2019-07-18"


def test_a_brand_new_note_is_dated_today(cfg, q, monkeypatch):
    """El otro lado de la regla: sin nada en disco, la fecha es hoy."""
    extraction(monkeypatch, PAGE)
    no_pictures(monkeypatch)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert read_note(result.path).saved == TODAY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline.py -q -k "keeps_the_day or keeps_its_date or dated_today"`
Expected: los dos primeros FAIL (`assert '2026-10-05' == '2019-07-18'`), el
tercero PASS.

- [ ] **Step 3: Write minimal implementation**

En `_partial_note`, agregar el parámetro y usarlo:

```python
def _partial_note(cfg: Config, link: str, url: str, content: str,
                  page: Extracted | None, saved: str | None = None) -> Note:
    """La nota que siempre se puede escribir: la URL, más lo que haya llegado.

    `saved` lo pasa quien ya sabe de cuándo es este link -- un reproceso, que
    lee la fecha de la nota en disco, o una importación, que la lee del chat.
    """
    return Note(
        ...
        saved=(saved or _today()),
        ...
    )
```

En `_process`, antes de armar el `Note`:

```python
    # Una nota se guardó cuando se guardó: reanalizarla no la vuelve a
    # guardar. Sin esto, un lote importado con sus fechas reales se apila
    # entero en el día del análisis.
    kept_date = existing[1].saved if existing else None
```

y en el `Note(...)`: `saved=(kept_date or _today()),`

En `_give_up`, pasar la fecha al parcial:

```python
    note = _partial_note(cfg, link, url, mode, page,
                         saved=(existing[1].saved if existing else None))
```

`_give_up` hoy no recibe `existing`; recibe `kept` y `target`. Agregar el
parámetro `saved: str | None = None` a `_give_up` y pasarlo desde las tres
llamadas de `_process`, que sí tiene `existing`:

```python
def _give_up(cfg: Config, q: Queue, link: str, url: str, mode: str,
             page: Extracted | None, reason: str, kept: Note | None,
             target: Path | None, saved: str | None = None) -> Result:
```

y en `_process` las tres pasan `saved=kept_date`. Calcular `kept_date` arriba
de todo, junto a `kept`, para que las tres ramas lo tengan.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: PASS, todos.

- [ ] **Step 5: Mutate the fix**

| Mutante | Qué cambia | Tiene que morir en |
|---|---|---|
| m1 | `saved=(kept_date or _today())` → `saved=_today()` | `keeps_the_day_it_was_saved` |
| m2 | `saved=(saved or _today())` → `saved=_today()` | `keeps_its_date` |
| m3 | `kept_date = existing[1].saved if existing else None` → `= None` | los dos |

- [ ] **Step 6: Run the whole suite and commit**

```bash
~/.local/share/oknowledge/venv/bin/python -m pytest -q
git add src/oknowledge/pipeline.py tests/test_pipeline.py
git commit -m "fix: keep the day a note was saved when it is reprocessed"
```

---

## Tarea 4: La escritura en bloque

**Files:**
- Modify: `src/oknowledge/pipeline.py`
- Test: `tests/test_import.py` (nuevo)

**Interfaces:**
- Consumes:
  - de la Tarea 2 — `Imported(url, sent, comment, sender, raw, bare)`
  - de la Tarea 3 — `_partial_note(cfg, link, url, content, page, saved=None)`
  - lo que ya existe — `vault.all_notes(cfg) -> list[Note]`,
    `vault.write_note(cfg, note, language, path=None) -> Path`,
    `vault.rebuild_indexes(cfg, language) -> RebuildResult`,
    `queue.Queue.enqueue(link_id, url, content) -> QueueEntry`,
    `queue.Queue.set_status(link_id, status, error=None, title=None)`,
    `queue.Queue.get(link_id) -> QueueEntry | None`,
    `queue.Queue.lock(link_id)` (context manager, levanta `Locked`),
    `urls.normalize(url) -> str`, `urls.link_id(url) -> str`
- Produces:
  - `@dataclass ImportResult` con `found: int`, `saved: int`, `already: int`,
    `duplicated: int`, `failed: list[tuple[str, str]]`
  - `def import_links(cfg, items: list[Imported], queue: Queue | None = None) -> ImportResult`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_import.py`:

```python
"""Escribir un lote de links importados.

Lo que esta función tiene que lograr es barato: los pasos caros -- escanear el
vault y reconstruir los índices -- se pagan una vez para el lote y no una vez
por link. Lo que NO puede perder son las garantías: sólo escribe adentro de
oknowledge/, deduplica, y deja entrada en la cola para que retry pueda
terminar cada uno.
"""

import pytest

from oknowledge.config import Config
from oknowledge.pipeline import import_links
from oknowledge.queue import Queue
from oknowledge.urls import link_id
from oknowledge.vault import read_note
from oknowledge.whatsapp import Imported


def item(url, sent="2019-07-18", comment="", sender="Fer", bare=False):
    return Imported(url=url, sent=sent, comment=comment, sender=sender,
                    raw=url, bare=bare)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "state")


def test_three_links_become_three_partial_notes_with_their_dates(cfg, q):
    result = import_links(cfg, [
        item("https://a.com/x", sent="2019-07-18"),
        item("https://b.com/y", sent="2021-03-02"),
        item("https://c.com/z", sent="2025-11-30"),
    ], queue=q)

    assert (result.found, result.saved, result.already) == (3, 3, 0)
    notes = sorted((read_note(p) for p in cfg.links_dir.glob("*.md")),
                   key=lambda n: n.saved)
    assert [n.saved for n in notes] == ["2019-07-18", "2021-03-02", "2025-11-30"]
    assert {n.status for n in notes} == {"partial"}
    assert {n.category for n in notes} == {"Sin clasificar"}


def test_the_comment_becomes_the_summary_and_stays_in_the_body(cfg, q):
    """El resumen lo reescribe el análisis; el cuerpo no."""
    import_links(cfg, [item("https://a.com/x", comment="mirá esto para el gym")],
                 queue=q)

    note = read_note(next(cfg.links_dir.glob("*.md")))
    assert note.summary == "mirá esto para el gym"
    assert note.body == "mirá esto para el gym"


def test_a_message_with_no_comment_gets_the_usual_partial_summary(cfg, q):
    import_links(cfg, [item("https://a.com/x", comment="")], queue=q)

    note = read_note(next(cfg.links_dir.glob("*.md")))
    assert "retry" in note.summary
    assert note.body is None


def test_every_link_leaves_a_queue_entry_so_retry_can_finish_it(cfg, q):
    import_links(cfg, [item("https://a.com/x")], queue=q)

    entry = q.get(link_id("https://a.com/x"))
    assert entry is not None
    assert entry.status == "partial"


def test_a_link_already_in_the_vault_is_counted_and_not_rewritten(cfg, q):
    """Por mtime, no por contenido: un write que da los mismos bytes es un write."""
    import_links(cfg, [item("https://a.com/x")], queue=q)
    path = next(cfg.links_dir.glob("*.md"))
    before = path.stat().st_mtime_ns

    result = import_links(cfg, [item("https://a.com/x", sent="2025-01-01")], queue=q)

    assert (result.saved, result.already) == (0, 1)
    assert path.stat().st_mtime_ns == before


def test_the_same_link_twice_in_the_chat_keeps_the_oldest_date(cfg, q):
    """Es cuándo lo guardó por primera vez."""
    result = import_links(cfg, [
        item("https://a.com/x", sent="2021-05-05"),
        item("https://a.com/x", sent="2019-07-18"),
    ], queue=q)

    assert (result.found, result.saved, result.duplicated) == (2, 1, 1)
    assert read_note(next(cfg.links_dir.glob("*.md"))).saved == "2019-07-18"


def test_a_queue_entry_written_during_the_run_blocks_a_second_note(cfg, q):
    """Cierra la ventana entre el escaneo inicial y la escritura."""
    q.enqueue(link_id("https://a.com/x"), "https://a.com/x", "full")
    q.set_status(link_id("https://a.com/x"), "ok")

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert (result.saved, result.already) == (0, 1)
    assert list(cfg.links_dir.glob("*.md")) == []


def test_an_old_queue_entry_with_no_note_does_not_block_the_link(cfg, q, monkeypatch):
    """Una nota borrada a mano tiene que poder volver: el vault es la verdad."""
    q.enqueue(link_id("https://a.com/x"), "https://a.com/x", "full")
    q.set_status(link_id("https://a.com/x"), "ok")
    entry = q.get(link_id("https://a.com/x"))
    entry.updated = "2019-01-01T00:00:00.000+00:00"
    q._write(entry)

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert (result.saved, result.already) == (1, 0)


def test_the_indexes_are_rebuilt_once_for_the_whole_batch(cfg, q, monkeypatch):
    """La razón de existir de esta función: 1215 veces son 19 minutos."""
    calls = []
    real = __import__("oknowledge.pipeline", fromlist=["x"]).rebuild_indexes

    def counted(config, language):
        calls.append(language)
        return real(config, language)

    monkeypatch.setattr("oknowledge.pipeline.rebuild_indexes", counted)

    import_links(cfg, [item(f"https://a{n}.com/x") for n in range(10)], queue=q)

    assert len(calls) == 1


def test_one_note_that_cannot_be_written_does_not_stop_the_others(cfg, q, monkeypatch):
    real = __import__("oknowledge.pipeline", fromlist=["x"]).write_note
    seen = []

    def boom(config, note, language, path=None):
        seen.append(note.id)
        if len(seen) == 2:
            raise OSError("no space left on device")
        return real(config, note, language, path=path)

    monkeypatch.setattr("oknowledge.pipeline.write_note", boom)

    result = import_links(cfg, [item(f"https://a{n}.com/x") for n in range(3)],
                          queue=q)

    assert result.saved == 2
    assert len(result.failed) == 1
    assert "no space left" in result.failed[0][1]


def test_nothing_is_written_outside_the_managed_folder(cfg, q, tmp_path):
    """links/ apuntado a otro lado es un hábito de Obsidian, no un ataque."""
    outside = tmp_path / "outside"
    outside.mkdir()
    cfg.links_dir.rmdir()
    cfg.links_dir.symlink_to(outside)

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert list(outside.iterdir()) == []
    assert result.saved == 0
    assert len(result.failed) == 1


def test_an_empty_batch_is_not_an_error(cfg, q):
    result = import_links(cfg, [], queue=q)

    assert (result.found, result.saved, result.already) == (0, 0, 0)


def test_a_url_that_normalizes_to_the_same_link_is_one_note(cfg, q):
    """normalize() saca los utm: el mismo link mandado dos veces es uno."""
    result = import_links(cfg, [
        item("https://a.com/x?utm_source=wa"),
        item("https://a.com/x"),
    ], queue=q)

    assert result.saved == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_import.py -q`
Expected: FAIL con `ImportError: cannot import name 'import_links'`

- [ ] **Step 3: Write minimal implementation**

Agregar a `src/oknowledge/pipeline.py`. Primero el import, al lado de los que
ya están:

```python
from .whatsapp import Imported
```

Después, arriba de `retry()`:

```python
@dataclass
class ImportResult:
    """Qué pasó con un lote importado. Ningún link se va sin figurar acá."""

    found: int = 0                              # links que traía el lote
    saved: int = 0                              # notas nuevas escritas
    already: int = 0                            # ya estaban en el vault o tomados
    duplicated: int = 0                         # repetidos dentro del lote
    failed: list[tuple[str, str]] = field(default_factory=list)   # (url, por qué)


def import_links(cfg: Config, items: list[Imported],
                 queue: Queue | None = None) -> ImportResult:
    """Escribir un lote de links importados como notas parciales.

    No llama a add() por link, y la razón está medida: add() paga dos
    escaneos completos del vault -- find_note() para deduplicar y
    rebuild_indexes() al guardar -- y reescribe todos los índices, cada vez.
    Con 1215 links eso es cuadrático: ~19 minutos de puro trámite y 1215
    tandas de escrituras dentro del vault de Obsidian.

    Acá los pasos caros se pagan una vez para el lote. Lo que no se abarata
    son las garantías: write_note() sigue siendo la única puerta de escritura
    y por lo tanto sigue pasando por ensure_inside_root y por el marcador, se
    deduplica por id, se toma el candado de cada link, y cada uno deja
    entrada en la cola para que retry() lo pueda terminar.
    """
    q = queue or Queue()
    started = _now_iso()
    result = ImportResult(found=len(items))

    # Un escaneo, no uno por link. Si el vault no se puede leer, no hay forma
    # de deduplicar, y escribir sin deduplicar es la única cosa que este
    # proyecto no hace: duplicar una nota.
    try:
        existing = {note.id for note in all_notes(cfg)}
    except OSError as error:
        result.failed.append(("", f"the vault could not be read ({_typed(error)})"))
        return result

    # Dedup dentro del lote, con la fecha más vieja: es cuándo lo guardó por
    # primera vez. normalize() ya saca los utm, así que dos spellings del
    # mismo link caen en el mismo id.
    wanted: dict[str, Imported] = {}
    for one in items:
        clean = normalize(one.url)
        if not clean:
            result.failed.append((one.url, "not a usable URL"))
            continue
        link = link_id(clean)
        before = wanted.get(link)
        if before is None:
            wanted[link] = replace(one, url=clean)
        else:
            result.duplicated += 1
            if one.sent < before.sent:
                wanted[link] = replace(one, url=clean)

    mode = cfg.default_content
    for link, one in wanted.items():
        if link in existing:
            result.already += 1
            continue
        try:
            with q.lock(link):
                # La cola como índice barato: cierra la ventana entre el
                # escaneo de arriba y ahora, porque add() siempre encola.
                # Sólo cuenta si la entrada es de esta corrida: una entrada
                # vieja de una nota que el usuario borró no tiene que impedir
                # que el link vuelva, porque el vault es la fuente de verdad.
                entry = q.get(link)
                if entry is not None and entry.updated >= started:
                    result.already += 1
                    continue
                note = _partial_note(cfg, link, one.url, mode, None, saved=one.sent)
                if one.comment:
                    note.summary = one.comment
                    note.body = one.comment
                write_note(cfg, note, cfg.language)
                q.enqueue(link, one.url, mode)
                q.set_status(link, "partial", error="imported, not analysed yet",
                             title=note.title)
                result.saved += 1
        except Locked:
            result.already += 1
        except Exception as error:
            # Un link que no se pudo escribir se reporta y la corrida sigue:
            # 1214 guardados y uno reportado es mejor que 1215 sin guardar.
            result.failed.append((one.url, _typed(error)))

    if result.saved:
        _reindex(cfg)        # una vez, para el lote
    return result
```

De los imports de `pipeline.py`, `dataclass`/`field` de `dataclasses`,
`all_notes` de `.vault` y `Locked` de `.queue` ya están; el único que falta es
`replace`, que pasa a `from dataclasses import dataclass, field, replace`.
`_now_iso()` no existe: agregarlo al lado de `_today()`:

```python
def _now_iso() -> str:
    """El mismo formato que escribe la cola, para poder comparar como strings."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_import.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Mutate the guards that matter**

| Mutante | Qué cambia | Tiene que morir en |
|---|---|---|
| m1 | `if link in existing` → `if False` | `already_in_the_vault_is_counted_and_not_rewritten` |
| m2 | `entry.updated >= started` → `entry is not None` | `an_old_queue_entry_with_no_note_does_not_block` |
| m3 | `entry.updated >= started` → borrado el chequeo entero | `a_queue_entry_written_during_the_run_blocks` |
| m4 | `if one.sent < before.sent` → `>` | `keeps_the_oldest_date` |
| m5 | `_reindex(cfg)` sacado del final | que algún test mire los índices — si ninguno lo hace, **agregar uno** que verifique que el índice de categoría existe después de importar |
| m6 | `except Exception` → `raise` | `one_note_that_cannot_be_written_does_not_stop_the_others` |

m5 es el que más probablemente sobreviva. Si sobrevive, el test que falta es:

```python
def test_the_batch_leaves_its_category_index_written(cfg, q):
    import_links(cfg, [item("https://a.com/x")], queue=q)

    assert list(cfg.root.glob("*.md")), "no index was written"
```

- [ ] **Step 6: Measure that it is actually fast**

El punto de la tarea es el tiempo. Medirlo una vez, con un script de nombre
único en el scratchpad, no en el repo:

```python
import time
# 500 links en un vault vacío, con un Queue en tmp
t0 = time.perf_counter()
import_links(cfg, [item(f"https://a{n}.com/x") for n in range(500)], queue=q)
print(f"{time.perf_counter() - t0:.1f}s para 500")
```

Expected: segundos, no minutos. Si pasa de ~30 s para 500, algo quedó
escaneando por link: revisar que `all_notes` se llame una sola vez.

- [ ] **Step 7: Run the whole suite and commit**

```bash
~/.local/share/oknowledge/venv/bin/python -m pytest -q
git add src/oknowledge/pipeline.py tests/test_import.py
git commit -m "feat: write a batch of imported links in one pass"
```

---

## Tarea 5: El comando `oknowledge import`

**Files:**
- Modify: `src/oknowledge/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes:
  - de la Tarea 2 — `whatsapp.parse(text) -> Scan`, `whatsapp.BadExport`,
    `Scan(links, suspicious, messages, day_first, assumed)`,
    `Imported(url, sent, comment, sender, raw, bare)`
  - de la Tarea 4 — `pipeline.import_links(cfg, items, queue=None) -> ImportResult`,
    `ImportResult(found, saved, already, duplicated, failed)`
- Produces: el subcomando `import` con `--dry-run` y `--json`.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_cli.py`:

```python
# --- importar un export de WhatsApp -----------------------------------------

EXPORT = """\
18/7/2019, 11:36 - Fer: https://scratux.org/#download
23/7/2019, 11:39 - Fer: sudo chkrootkit
21/7/2019, 13:50 - Fer: mirá youtu.be/abc
24/7/2019, 10:00 - Fer: el config.json que te mandé
"""


def test_import_saves_the_links_with_their_dates(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    assert main(["import", str(export)]) == 0

    out = capsys.readouterr().out
    assert "2 links in 4 messages" in out
    assert "2 saved, 0 already there" in out
    assert "1 of them was written without a scheme" in out
    assert "1 message looks like it had a link" in out
    saved = sorted(n.saved for n in all_notes(cfg))
    assert saved == ["2019-07-18", "2019-07-21"]


def test_import_says_how_the_dates_were_read(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export)])

    assert "dates read as day/month" in capsys.readouterr().out


def test_import_marks_an_assumed_date_order(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("7/8/2019, 11:36 - Fer: https://e.com/x\n", encoding="utf-8")

    main(["import", str(export)])

    assert "(assumed)" in capsys.readouterr().out


def test_a_dry_run_writes_nothing_and_lists_the_three_groups(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    assert main(["import", str(export), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert list(cfg.links_dir.glob("*.md")) == []
    assert "https://scratux.org/#download" in out
    assert "youtu.be/abc" in out                 # el original, no el https://
    assert "config.json" in out                  # el sospechoso
    assert "nothing was written" in out


def test_import_json_is_one_object(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["found"] == 2
    assert payload["saved"] == 2
    assert payload["messages"] == 4
    assert payload["day_first"] is True


def test_a_file_that_is_not_there_is_a_config_error(cfg, tmp_path, capsys):
    assert main(["import", str(tmp_path / "nope.txt")]) == 2
    assert "nope.txt" in capsys.readouterr().err


def test_a_file_that_is_not_an_export_names_the_format(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("esto no es un export\n", encoding="utf-8")

    assert main(["import", str(export)]) == 2

    assert "D/M/YYYY" in capsys.readouterr().err


def test_a_file_whose_dates_contradict_each_other_is_refused(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("18/7/2019, 11:36 - Fer: https://e.com/x\n"
                      "7/18/2019, 11:36 - Fer: https://e.com/y\n", encoding="utf-8")

    assert main(["import", str(export)]) == 2

    error = capsys.readouterr().err
    assert "18/7/2019" in error and "7/18/2019" in error
    assert list(cfg.links_dir.glob("*.md")) == []


def test_a_byte_that_is_not_utf8_does_not_abort_the_import(cfg, tmp_path, capsys):
    """Seis años de chat pueden traer uno. No vale perder 1215 links por eso."""
    export = tmp_path / "chat.txt"
    export.write_bytes(
        "18/7/2019, 11:36 - Fer: https://e.com/x\n".encode()
        + b"19/7/2019, 11:36 - Fer: \xff\xfe roto\n"
        + "20/7/2019, 11:36 - Fer: https://e.com/y\n".encode())

    assert main(["import", str(export)]) == 0

    assert len(all_notes(cfg)) == 2


def test_an_import_that_saved_nothing_because_it_failed_exits_one(cfg, tmp_path,
                                                                  capsys, monkeypatch):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    def boom(config, note, language, path=None):
        raise OSError("no space left on device")

    monkeypatch.setattr("oknowledge.pipeline.write_note", boom)

    assert main(["import", str(export)]) == 1

    assert "no space left" in capsys.readouterr().err
```

Agregar `from oknowledge.vault import RebuildResult, all_notes, write_note` al
import de `vault` que ya está en el archivo.

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_cli.py -q -k import`
Expected: FAIL con `SystemExit: 2` y `invalid choice: 'import'`

- [ ] **Step 3: Write minimal implementation**

En `_parser()`, después del parser de `icons`:

```python
    import_cmd = subs.add_parser("import", help="import the links out of a WhatsApp export")
    import_cmd.add_argument("file", type=Path)
    import_cmd.add_argument("--dry-run", action="store_true",
                            help="list what it would capture and write nothing")
    import_cmd.add_argument("--json", action="store_true")
```

En `main()`, con los demás:

```python
        if args.command == "import":
            return _import(cfg, args)
```

Y la función, al lado de `_icons`:

```python
def _import(cfg, args) -> int:
    """Importar los links de un export de WhatsApp.

    Imprime datos de los dos lados: `messages`, los sospechosos y el orden de
    fecha salen del Scan del parser; `saved`, `already` y `failed` del
    ImportResult de la escritura.
    """
    try:
        # errors="replace": seis años de chat pueden traer un byte que no es
        # UTF-8, y perder 1215 links por uno es la clase de nada silenciosa
        # que este proyecto no hace.
        text = args.file.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        print(f"oknowledge: cannot read {_clean(args.file)}: {error}", file=sys.stderr)
        return 2

    try:
        scan = parse(text)
    except BadExport as error:
        print(f"oknowledge: {error}", file=sys.stderr)
        return 2

    order = ("day/month" if scan.day_first else "month/day")
    reading = f"dates read as {order}{' (assumed)' if scan.assumed else ''}"
    bare = sum(1 for one in scan.links if one.bare)

    if args.dry_run:
        _dry_run(scan, reading)
        return 0

    result = import_links(cfg, scan.links)
    if args.json:
        print(json.dumps({"found": result.found, "saved": result.saved,
                          "already": result.already,
                          "duplicated": result.duplicated,
                          "failed": [list(row) for row in result.failed],
                          "messages": scan.messages,
                          "suspicious": scan.suspicious,
                          "day_first": scan.day_first, "assumed": scan.assumed},
                         ensure_ascii=False))
    else:
        print(f"{_count(result.found, 'link', 'links')} in "
              f"{_count(scan.messages, 'message', 'messages')} ({reading})")
        print(f"{result.saved} saved, {result.already} already there, "
              f"{result.duplicated} repeated in the chat")
        if bare:
            print(f"{_count(bare, 'of them was', 'of them were')} written "
                  "without a scheme")
        if scan.suspicious:
            print(f"{_count(len(scan.suspicious), 'message looks', 'messages look')} "
                  "like it had a link and did not match (see --dry-run)")
    for url, why in result.failed:
        print(f"not saved: {_clean(url)}: {_clean(why)}", file=sys.stderr)
    return 1 if result.failed and not result.saved else 0


def _dry_run(scan, reading: str) -> None:
    """Las tres listas que hacen revisable al parser.

    Los completos son los seguros; los sueltos son donde puede haber un falso
    positivo; los sospechosos son donde puede haber un link perdido. El
    usuario mira las dos últimas antes de escribir nada.
    """
    print(f"{_count(len(scan.links), 'link', 'links')} in "
          f"{_count(scan.messages, 'message', 'messages')} ({reading})")
    full = [one for one in scan.links if not one.bare]
    bare = [one for one in scan.links if one.bare]
    for title, group in (("with a scheme", full), ("without a scheme", bare)):
        if group:
            print(f"\n{_count(len(group), 'link', 'links')} {title}:")
            for one in group:
                print(f"  {one.sent}  {_clean(one.raw)}")
    if scan.suspicious:
        print(f"\n{_count(len(scan.suspicious), 'message', 'messages')} "
              "that looked like a link and did not match:")
        for text in scan.suspicious:
            print(f"  {_clean(text)}")
    print("\nnothing was written")
```

Los imports arriba de `cli.py`:

```python
from .pipeline import ImportResult, Result, add, backfill_icons, import_links, retry
from .whatsapp import BadExport, parse
```

`_count(n, singular, plural)` ya existe y devuelve `"1 link"` / `"2 links"`.
Para las frases que necesitan concordancia de verbo —"1 of them **was**" vs
"2 of them **were**"— se le pasan las dos formas completas, como arriba.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_cli.py -q -k import`
Expected: PASS, 10 tests.

- [ ] **Step 5: Update the README**

En la tabla de comandos de `README.md`, después de la fila de `icons`:

```markdown
| `oknowledge import FILE [--dry-run] [--json]` | import the links out of a WhatsApp export, dated when you sent them |
```

Y abajo de la tabla, un párrafo propio, porque el `--dry-run` merece que se
sepa que existe:

```markdown
**`import` reads a WhatsApp chat export** (`Export chat` → `Without media`,
which gives a `_chat.txt`) and saves every link in it as an unfinished note
dated the day you sent it. Phone numbers, notes to self and anything else
without a link are skipped. Nothing is analysed: that is `retry`'s job, and
`retry --limit 50` does it in batches.

Run it with `--dry-run` first. It lists what it would capture in three
groups — the links written with `https://`, the ones written as a bare
domain, and the messages that looked like they had a link and did not match.
The second group is where a false positive would be; the third is where a
missed link would be.
```

- [ ] **Step 6: Run the whole suite and commit**

```bash
~/.local/share/oknowledge/venv/bin/python -m pytest -q
git add src/oknowledge/cli.py tests/test_cli.py README.md
git commit -m "feat: add the import command for a WhatsApp export"
```

---

## Tarea 6: `retry --limit N`

**Files:**
- Modify: `src/oknowledge/pipeline.py` (`retry`)
- Modify: `src/oknowledge/cli.py` (`_parser`, `_retry`)
- Modify: `tests/test_pipeline.py`, `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: lo que ya existe — `retry(cfg, queue=None) -> list[Result]`,
  `vault.all_notes(cfg) -> list[Note]`.
- Produces: `retry(cfg, queue=None, limit: int | None = None) -> list[Result]`
  y la opción `--limit N` del CLI.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_pipeline.py`:

```python
# --- analizar de a tandas ----------------------------------------------------


def _three_partials(cfg, q, monkeypatch, dates):
    """Tres links sin terminar, con las fechas que se piden."""
    extraction(monkeypatch, Unreadable("503"))
    no_pictures(monkeypatch)
    for n, when in enumerate(dates):
        add(cfg, f"https://e{n}.com/x", queue=q)
    for path in cfg.links_dir.glob("*.md"):
        note = read_note(path)
        when = dates[int(note.url[len("https://e")])]
        path.write_text(path.read_text(encoding="utf-8").replace(
            f"saved: {TODAY}", f"saved: {when}"), encoding="utf-8")


def test_retry_with_a_limit_stops_after_that_many(cfg, q, monkeypatch):
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER, ANSWER, ANSWER]

    results = retry(cfg, queue=q, limit=2)

    assert len(results) == 2
    assert len(q.unfinished()) == 1


def test_retry_with_a_limit_takes_the_newest_first(cfg, q, monkeypatch):
    """Los links más nuevos son los que más chance tienen de estar vivos."""
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER, ANSWER, ANSWER]

    results = retry(cfg, queue=q, limit=1)

    assert results[0].url == "https://e2.com/x"


def test_a_link_with_no_note_at_all_goes_before_the_dated_ones(cfg, q, monkeypatch):
    """Una entrada sin nota es la regla de que no se pierde un link, pendiente."""
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])
    q.enqueue("abcdef123456", "https://huerfano.com/x", "full")
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER] * 4

    results = retry(cfg, queue=q, limit=1)

    assert results[0].url == "https://huerfano.com/x"


def test_an_entry_already_settled_does_not_use_up_the_quota(cfg, q, monkeypatch):
    """El cupo cuenta trabajo hecho, no intentos."""
    extraction(monkeypatch, PAGE)
    no_pictures(monkeypatch)
    done = add(cfg, "https://e0.com/x", queue=q)
    assert done.status == "ok"
    q.set_status(done.id, "partial")          # la cola miente, la nota está bien
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER] * 4

    results = retry(cfg, queue=q, limit=1)

    analysed = [r for r in results if r.status == "ok" and r.engine]
    assert len(analysed) == 1


def test_retry_without_a_limit_behaves_exactly_as_before(cfg, q, monkeypatch):
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER] * 3

    results = retry(cfg, queue=q)

    assert len(results) == 3
    assert q.unfinished() == []


def test_a_limit_of_zero_does_nothing(cfg, q, monkeypatch):
    _three_partials(cfg, q, monkeypatch, ["2019-01-01", "2021-01-01", "2025-01-01"])

    assert retry(cfg, queue=q, limit=0) == []
    assert len(q.unfinished()) == 3
```

Y a `tests/test_cli.py`:

```python
def test_retry_limit_is_passed_through(cfg, monkeypatch, capsys):
    seen = {}

    def fake(config, queue=None, limit=None):
        seen["limit"] = limit
        return []

    monkeypatch.setattr("oknowledge.cli.retry", fake)

    assert main(["retry", "--limit", "50"]) == 0

    assert seen["limit"] == 50


def test_retry_refuses_a_negative_limit(cfg, capsys):
    assert main(["retry", "--limit", "-1"]) == 2
    assert "limit" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline.py tests/test_cli.py -q -k "limit or newest or quota or no_note_at_all"`
Expected: FAIL con `TypeError: retry() got an unexpected keyword argument 'limit'`

- [ ] **Step 3: Write minimal implementation**

En `retry()`, cambiar la firma y el loop:

```python
def retry(cfg: Config, queue: Queue | None = None,
          limit: int | None = None) -> list[Result]:
    """Finish every link the queue still owes, newest first, and settle the
    ones only the bookkeeping thinks are owed.

    `limit` corta después de esa cantidad de links **terminados**, no
    intentados: una entrada que resultó estar ya saldada no consume cupo,
    porque reconciliar bookkeeping no es trabajo. Eso es lo que permite
    analizar un lote importado de a 50 por día sin que un día se vaya en
    entradas viejas.
    """
```

Después de armar `owed`, ordenarlo:

```python
    # De lo más nuevo a lo más viejo. La fecha no está en la cola -- un lote
    # importado tiene el mismo `updated` para todos -- así que sale del
    # `saved` de la nota: un escaneo por corrida, no uno por link. Una
    # entrada sin nota va primero: es un link que todavía no llegó al vault,
    # y eso es más urgente que cualquier fecha.
    try:
        dates = {note.id: note.saved for note in all_notes(cfg)}
    except OSError:
        dates = {}
    ordered = sorted(owed.values(), key=lambda e: dates.get(e.id, "9999-99-99"),
                     reverse=True)
```

Y el loop, contando terminados:

```python
    done = 0
    for entry in ordered:
        if limit is not None and done >= limit:
            break
        try:
            settled = _reconcile(cfg, q, entry)
            if settled is not None:
                results.append(settled)
                continue                  # bookkeeping, no trabajo: no gasta cupo
            results.append(add(cfg, entry.url, content=entry.content,
                               reprocess=True, queue=q))
            done += 1
        except Exception as error:
            results.append(_failed(q, entry, error))
            done += 1                     # intentarlo y fallar sí es trabajo
    return results
```

En `cli.py`, el flag:

```python
    retry_cmd.add_argument("--limit", type=int, metavar="N",
                           help="finish at most N links and stop")
```

y en `_retry`:

```python
def _retry(cfg, args) -> int:
    if args.limit is not None and args.limit < 0:
        print("oknowledge: --limit cannot be negative", file=sys.stderr)
        return 2
    results = retry(cfg, limit=args.limit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q`
Expected: PASS, toda la suite. Los tests de `retry` que ya existían no cambian
de significado porque `limit=None` es el comportamiento de siempre.

- [ ] **Step 5: Mutate the limit**

| Mutante | Qué cambia | Tiene que morir en |
|---|---|---|
| m1 | `done >= limit` → `done > limit` | `stops_after_that_many` |
| m2 | `done += 1` después del `add` → borrado | `stops_after_that_many` |
| m3 | el `continue` del reconcile → `done += 1` antes | `does_not_use_up_the_quota` |
| m4 | `reverse=True` → `reverse=False` | `takes_the_newest_first` |
| m5 | `dates.get(e.id, "9999-99-99")` → `dates.get(e.id, "")` | `no_note_at_all_goes_before` |

- [ ] **Step 6: Update the README and commit**

En la fila de `retry` de la tabla:

```markdown
| `oknowledge retry [--limit N] [--json]` | finish the links left half done, newest first (see the note below) |
```

Y agregar al párrafo que ya explica `retry`:

```markdown
`--limit N` finishes at most N links and stops, newest first. That is how a
large import gets analysed: 1215 links are 10 to 20 hours of fetching and
model time, so `oknowledge retry --limit 50` once a day works through them
without a run that never ends. The quota counts links it actually worked on,
so an entry that turned out to be already saved does not use one up.
```

```bash
~/.local/share/oknowledge/venv/bin/python -m pytest -q
git add src/oknowledge/pipeline.py src/oknowledge/cli.py tests/ README.md
git commit -m "feat: finish links in batches with retry --limit"
```

---

## Cierre: probarlo con el archivo de verdad

No es una tarea con tests; es el paso que no se puede saltear antes de decir
que está listo. El archivo real tiene 1215 links y seis años de ruido, que es
exactamente lo que ningún test sintético tiene.

- [ ] **Step 1: `--dry-run` sobre el export real**

```bash
~/.local/share/oknowledge/venv/bin/oknowledge import /ruta/al/chat.txt --dry-run
```

Mirar, en este orden:

1. ¿El orden de fecha dice `day/month` y **sin** `(assumed)`? Si dice
   `(assumed)` sobre un archivo de seis años, el detector no encontró
   evidencia y algo está mal en la limpieza de invisibles.
2. ¿La cuenta de links se parece a 1215? Si da mucho menos, hay links que el
   matcher no ve. Si da mucho más, hay falsos positivos.
3. **La lista "without a scheme"**: ¿hay algo que claramente no es un link?
   Eso se arregla sacando el TLD de `TLDS` o agregándolo a `EXTENSIONS`.
4. **La lista de sospechosos**: ¿hay un link de verdad ahí? Eso se arregla
   agregando el TLD a `TLDS`.

- [ ] **Step 2: Ajustar las dos listas si hace falta, con un test por caso**

Cualquier cosa que aparezca mal en el paso anterior entra como una fila nueva
en el test parametrizado `test_what_counts_as_a_link` de la Tarea 2, con el
dominio real que lo motivó, y después se ajusta la lista. El test primero.

- [ ] **Step 3: Importar de verdad, y verificar que no tocó ninguna nota**

Antes:

```bash
stat -c '%n %y' ~/Documents/obsidian_vaults/fer/oknowledge/links/*.md > /tmp/antes.txt
```

Importar, y después comparar. Las notas que ya estaban tienen que quedar
**idénticas al nanosegundo**: la importación escribe notas nuevas y no toca
las viejas.

- [ ] **Step 4: Una tanda chica de análisis**

```bash
~/.local/share/oknowledge/venv/bin/oknowledge retry --limit 5
```

Verificar que las 5 notas analizadas **conservaron su fecha de WhatsApp**.
Esto es la Tarea 3 probada contra el caso real, y es el que hace que la línea
de tiempo del próximo subsistema tenga sentido.

- [ ] **Step 5: Abrir la web y mirar**

```bash
~/.local/share/oknowledge/venv/bin/oknowledge serve --open
```

Con más de mil tarjetas, mirar que la grilla y el scroll del resumen sigan
andando, y que las fechas de las tarjetas vayan de 2019 a hoy.
