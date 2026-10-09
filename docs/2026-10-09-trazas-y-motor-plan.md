# Plan: trazas del pipeline, el motor en la nota, y elegir modelo de una lista

**Diseño:** `docs/2026-10-09-trazas-y-motor-design.md`

**Objetivo:** hacer visible lo que el pipeline ya sabe — qué está haciendo
mientras tarda, qué modelo contestó cada nota, y qué modelos hay para elegir.

**Rama:** `feat/mentions-search` (la actual, sin mergear).

## Restricciones que valen para todas las tareas

- `pytest -W error`, suite entera en verde antes de cada commit.
- **Cada test nuevo se muta.** Un test que no falla con el código roto no es
  evidencia. Se reporta qué mutación se corrió y qué pasó.
- Código y CLI en inglés; todo texto de interfaz pasa por `i18n.py` con su
  traducción al español.
- **Un link nunca se pierde.** Es la regla del módulo y la que este plan pone
  en más riesgo: el tracer es código nuevo en el camino crítico.
- Nada de líneas de atribución en los commits.
- Sin `logging` en el pipeline: el tracer es un callback que el llamador pasa.

## Dónde mirar con más cuidado

Cinco cosas que el diseño implica y que ninguna tarea prueba sola:

1. Un tracer que levanta en el peor momento (entre el análisis y la escritura).
2. Una carpeta de trazas que no se puede crear: disco lleno, permisos.
3. Un `prompt` que no es UTF-8 limpio llegando al archivo de traza.
4. Una nota vieja con `engine:` escrito a mano con un valor que no es un motor.
5. `opencode models` devolviendo basura, o 10.000 líneas.

Cada una tiene su test en la tarea que la toca; están anotadas ahí.

---

## Tarea 1 — El paso y el envoltorio que nunca levanta

**Archivos:** crear `src/oknowledge/trace.py` · test `tests/test_trace.py`

Nada del pipeline todavía: solo la pieza y su garantía.

- [ ] **Paso 1: el test que falla primero**

```python
def test_a_tracer_that_explodes_never_reaches_the_caller():
    def angry(step):
        raise RuntimeError("boom")
    safe = guarded(angry)
    safe(Step(link="a", name="extract", state="ok", seconds=1.0))   # no levanta


def test_no_tracer_costs_nothing():
    """Sin tracer no se arma ni un Step: el costo de no usarlo es un `if`."""
    built = []
    assert guarded(None) is SILENT
    SILENT(Step(link="a", name="x", state="ok", seconds=0.0))
```

- [ ] **Paso 2:** correrlo y ver que falla por `guarded` inexistente.
- [ ] **Paso 3:** `Step` como el diseño lo define, `SILENT = lambda step: None`
      y `guarded(fn)` que devuelve `SILENT` con `None` y si no un envoltorio
      con `try/except Exception`. `BaseException` pasa — un Ctrl-C es del
      usuario.
- [ ] **Paso 4:** verde.
- [ ] **Paso 5: mutar.** Sacar el `except`: el primer test tiene que fallar.
- [ ] **Paso 6:** commit.

---

## Tarea 2 — Emitir los pasos en `_process()`

**Archivos:** `src/oknowledge/pipeline.py` · test `tests/test_pipeline_trace.py`

**Consume:** `Step`, `guarded`, `SILENT` de la Tarea 1.
**Produce:** `add(..., trace=None)` y `retry(..., trace=None)`.

- [ ] **Paso 1: los tests primero.** Tres, y el primero es el que importa:

```python
def test_a_tracer_that_explodes_still_saves_the_note(tmp_path, cfg):
    """La prueba que justifica todo el envoltorio."""
    def angry(step):
        raise RuntimeError("boom")
    quiet = add(cfg, "https://a.test/x")
    loud = add(cfg, "https://a.test/y", trace=angry)
    assert loud.status == quiet.status
    assert loud.path is not None


def test_a_link_that_falls_through_to_the_second_engine_says_so_twice():
    steps = [s for s in seen if s.name == "analyze"]
    assert [(s.state, s.engine) for s in steps] == [
        ("start", "opencode"), ("fail", "opencode"),
        ("start", "ollama"), ("ok", "ollama"),
    ]
    assert "ling-3.1" in steps[1].detail        # el modelo, no solo el motor


def test_every_step_closes(cfg):
    """Ningún paso queda abierto, ni en el camino de falla."""
    for name in {s.name for s in seen}:
        opened = [s for s in seen if s.name == name and s.state == "start"]
        closed = [s for s in seen if s.name == name and s.state in ("ok", "fail")]
        assert len(opened) == len(closed), name
```

- [ ] **Paso 2:** correrlos, ver fallar por el parámetro inexistente.
- [ ] **Paso 3:** `trace` en `add()`, `_process()` y `retry()`; primera línea
      de cada uno `trace = guarded(trace)`. Emitir en los cinco límites del
      diseño. El reloj es `time.monotonic()`.
      `analyze_with_chain()` recibe el tracer y emite uno por vuelta del `for`.
- [ ] **Paso 4:** verde, y la suite entera también: `add()` cambió de firma.
- [ ] **Paso 5: mutar.** (a) sacar el `guarded()` de `add` — el primer test
      falla; (b) emitir `analyze` una vez por link en vez de por motor — el
      segundo falla; (c) no emitir el cierre en el camino de falla de
      `extract` — el tercero falla.
- [ ] **Paso 6:** commit.

---

## Tarea 3 — El archivo de prompt y respuesta

**Archivos:** `src/oknowledge/trace.py` · test `tests/test_trace_files.py`

- [ ] **Paso 1: los tests.**

```python
def test_a_huge_prompt_keeps_its_head_and_its_tail(tmp_path):
    body = write_trace(tmp_path, "abc123", url="…", engine="opencode",
                       model="m", prompt="A" * 500_000, reply="ok")
    text = body.read_text(encoding="utf-8")
    assert len(text.encode()) <= 256 * 1024
    assert "A" * 100 in text                    # la cabeza
    assert "recortado" in text                  # y lo dice


def test_a_prompt_that_is_not_clean_utf8_is_still_written(tmp_path):
    write_trace(tmp_path, "a", prompt="hola \udcff mundo", reply="")


def test_a_folder_that_cannot_be_created_is_not_an_error(tmp_path):
    (tmp_path / "trace").write_text("soy un archivo, no una carpeta")
    assert write_trace(tmp_path, "a", prompt="x", reply="y") is None


def test_the_sweep_keeps_the_last_ten_runs(tmp_path):
    ...
    assert len(list((tmp_path / "trace").iterdir())) == 10


def test_the_sweep_survives_a_folder_it_cannot_remove(tmp_path):
    ...                                          # no levanta
```

- [ ] **Paso 2–4:** rojo, implementar (`write_trace`, `sweep_traces`), verde.
      El recorte parte por el medio y deja marca. Escribir con
      `errors="replace"`, por el mismo motivo que el importador de WhatsApp.
- [ ] **Paso 5: mutar.** Tope quitado; recorte que se come la cola; `sweep`
      dejando 11; `except OSError` sacado de la creación de carpeta.
- [ ] **Paso 6:** commit.

---

## Tarea 4 — `engine` y `model` en la nota

**Archivos:** `model.py`, `vault.py`, `ai/__init__.py`, `pipeline.py` ·
tests en `tests/test_vault.py`, `tests/test_pipeline.py`

**Independiente de 1–3**: se puede hacer antes si conviene.

- [ ] **Paso 1: los tests.**

```python
def test_the_engine_and_model_survive_a_round_trip(tmp_path):
    note = Note(..., engine="opencode", model="opencode/ling-3.1-flash-free")
    assert read_note(write_note(cfg, note))[1].model == note.model


def test_a_note_written_before_this_existed_reads_as_empty(tmp_path):
    assert read_note(old_note_path)[1].engine == ""


def test_a_note_in_no_engine_does_not_carry_the_key(tmp_path):
    assert "engine:" not in write_note(cfg, note).read_text()


def test_an_engine_written_by_hand_as_a_list_does_not_break_the_read():
    """Punto 4 de 'dónde mirar': el vault se edita a mano."""
    assert read_note(weird)[1].engine == ""


def test_a_reprocess_overwrites_them_and_keeps_the_collections():
    ...
```

- [ ] **Paso 2–4:** rojo; `engine`/`model` en `Note` con default `""`, en
      `FRONTMATTER_ORDER` entre `content` y `status`, omitidos si vacíos;
      `analyze_with_chain()` devuelve `(Analysis, name, model)`;
      `_save()` los escribe. Verde.
- [ ] **Paso 5: mutar.** Escribir la clave vacía; no omitirla; preservarlos en
      un reproceso (el test de reproceso tiene que fallar); aceptar una lista.
- [ ] **Paso 6:** commit.

---

## Tarea 5 — El ícono en la tarjeta

**Archivos:** `templates/icon-engine-*.html` (3), `library.html`, `item.html`,
`embed.html`, `static/style.css`, `i18n.py` · test `tests/test_web_cards.py`

**Consume:** `Note.engine` / `Note.model` de la Tarea 4.

- [ ] **Paso 1: los tests.**

```python
def test_a_note_with_no_engine_draws_no_icon(client):
    assert "icon-engine" not in client.get("/").text


def test_the_model_is_in_the_title_of_the_icon(client):
    assert 'title="opencode · opencode/ling-3.1-flash-free"' in body


def test_an_unknown_engine_draws_nothing_rather_than_a_broken_include(client):
    """Una nota con `engine: pepe` escrito a mano no rompe la biblioteca."""


def test_the_icon_follows_the_theme(client):
    assert "currentColor" in body          # la lección del disquete
```

- [ ] **Paso 2–4:** rojo; tres SVG dibujados con `currentColor`, un mapa
      `engine -> plantilla` que ignora lo que no conoce, el `title` con motor y
      modelo. Verde.
- [ ] **Paso 5: mutar.** Color fijo en vez de `currentColor`; dibujar un ícono
      genérico ante un motor desconocido; sacar el `title`.
- [ ] **Paso 6:** commit.

---

## Tarea 6 — Las trazas en la página `/retry`

**Archivos:** `web/batch.py`, `web/app.py`, `templates/retry.html`,
`static/style.css`, `i18n.py` · test `tests/test_web_retry.py`

**Consume:** las Tareas 1–3.

- [ ] **Paso 1: los tests.**

```python
def test_the_lines_are_capped(progress):
    for i in range(500):
        progress.note(step(i))
    assert len(progress.lines()) == 200
    assert "499" in str(progress.lines()[0])      # lo nuevo arriba


def test_a_run_that_is_not_running_drops_what_arrives_late():
    ...


def test_the_page_says_the_traces_hold_the_page_text(client):
    """La casilla dice qué guarda, porque guarda tu contenido."""
    assert t("The trace files hold the full text of each page.") in body


def test_the_checkbox_is_off_unless_asked(client):
    ...
```

- [ ] **Paso 2–4:** rojo; `deque(maxlen=200)` en `Progress` bajo el mismo lock
      que ya usa; la casilla en el formulario; `run_batch` arma el tracer;
      la lista en la plantilla, lo nuevo arriba. Verde.
- [ ] **Paso 5: mutar.** `maxlen` quitado; orden invertido; casilla prendida
      por defecto; la advertencia sacada.
- [ ] **Paso 6:** commit.

---

## Tarea 7 — `models()` por motor

**Archivos:** `ai/opencode.py`, `ai/ollama.py`, `ai/api.py` ·
test `tests/test_ai_models.py`

- [ ] **Paso 1: los tests.**

```python
def test_a_server_that_is_not_there_lists_nothing_and_does_not_raise():
    assert OllamaEngine(model="m", url="http://127.0.0.1:1").models() == []


def test_a_listing_that_is_garbage_lists_nothing():
    """Punto 5 de 'dónde mirar'."""
    assert parse_opencode_models("\x00\x01 no soy una lista") == []


def test_a_listing_of_ten_thousand_lines_is_cut():
    assert len(parse_opencode_models("m\n" * 10_000)) == 200


def test_the_timeout_is_honoured():
    ...
```

- [ ] **Paso 2–4:** rojo; `models()` en los tres, cada uno con su timeout del
      diseño, todos devolviendo `[]` ante cualquier problema. Verde.
- [ ] **Paso 5: mutar.** Dejar escapar la excepción; sacar el timeout; sacar
      el tope de 200.
- [ ] **Paso 6:** commit.

---

## Tarea 8 — El `<datalist>` y el botón Buscar modelos

**Archivos:** `web/app.py`, `templates/settings.html`, `i18n.py`,
`src/oknowledge/models_cache.py` · test `tests/test_web_settings.py`

**Consume:** la Tarea 7.

- [ ] **Paso 1: los tests.** El que manda:

```python
def test_opening_settings_asks_no_engine_anything(client, monkeypatch):
    """12 segundos de espera para abrir Ajustes es la trampa de este diseño."""
    def forbidden(*a, **k):
        raise AssertionError("Ajustes consultó a un motor al abrir")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    client.get("/settings")


def test_the_cache_says_how_old_it_is(client):
    assert "2026-10-09" in client.get("/settings").text


def test_a_search_that_finds_nothing_says_so_and_keeps_the_box_typable():
    assert 'list="models-ollama"' in body       # el datalist sigue ahí, vacío
```

- [ ] **Paso 2–4:** rojo; `models.json` en el state dir con `{motor: {found,
      at}}`; `POST /settings/models/{engine}`; el `<input list>` + `<datalist>`
      en la plantilla; la fecha al lado del botón. Verde.
- [ ] **Paso 5: mutar.** Consultar al abrir (el primer test falla); cachear sin
      fecha; cambiar el `input` por un `select` (el tercero falla, porque ya no
      se puede escribir a mano).
- [ ] **Paso 6:** commit.

---

## Al final

- Suite entera con `-W error`.
- Probar a mano sobre un vault descartable: un lote con la casilla prendida,
  mirar la página mientras corre, abrir un archivo de traza.
- **No mergear ni pushear**: la integración la decidís vos.
