"""The interface language: English by default, Spanish opt-in.

The preference is not this project's: it lives in the shared Omarchy file that
all my plugins read. The English text is the key, so a missing translation
degrades to English and nothing breaks. This is a separate axis from the
language the AI writes summaries in (`[ai] language`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .atomic import atomic_write

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
        "Open original": "Abrir el original",
        "Open the note": "Abrir la nota",
        "Close": "Cerrar",
        "Key points": "Puntos clave",
        "Original content": "Contenido original",
        "Saved": "Guardado",
        "Incomplete": "Incompleto",
        "Delete": "Borrar",
        "Reprocess": "Reprocesar",
        "Edit tags": "Editar etiquetas",
        "Move to category": "Mover a categoría",
        "Rename": "Renombrar",
        "Merge into": "Fusionar con",
        "Save": "Guardar",
        "Engines": "Motores",
        "Interface language": "Idioma de la interfaz",
        "Summary language": "Idioma de los resúmenes",
        "Keep by default": "Guardar por defecto",
        "All": "Todo",
        "1 note could not be read and is not shown (%1)":
            "1 nota no se pudo leer y no se muestra (%1)",
        "%1 notes could not be read and are not shown (%2)":
            "%1 notas no se pudieron leer y no se muestran (%2)",
        "Nothing in this category": "No hay nada en esta categoría",
        "Nothing matches that filter": "No hay nada con ese filtro",
        "Not found": "No encontrado",
        "That link is not in your library.": "Ese link no está en tu biblioteca.",
        "Previous": "Anterior",
        "Next": "Siguiente",
        "Page %1 of %2": "Página %1 de %2",
        "The vault could not be read": "No se pudo leer el vault",
        "Check that the folder exists, is mounted and is readable.":
            "Revisá que la carpeta exista, esté montada y se pueda leer.",
        "Full": "Todo",
        "Summary": "Resumen",
        "Saved.": "Guardado.",
        "The note was moved to the trash folder inside your vault. "
        "You can restore it from Obsidian.":
            "La nota se movió a la carpeta trash de tu vault. "
            "La podés recuperar desde Obsidian.",
        "Re-running the analysis. The note stays pending until it finishes.":
            "Reprocesando. La nota queda pendiente hasta que termine.",
        'That name cannot be used as a category: at most 80 characters, no '
        'dots at either end, no control characters, and none of \\ / : * ? " < > |':
            'Ese nombre no sirve como categoría: 80 caracteres como máximo, sin '
            'puntos al principio ni al final, sin caracteres de control y '
            'ninguno de \\ / : * ? " < > |',
        "1 note moved.": "Se movió 1 nota.",
        "%1 notes moved.": "Se movieron %1 notas.",
        "1 note merged into a category that was already there.":
            "1 nota se fusionó con una categoría que ya existía.",
        "%1 notes merged into a category that was already there.":
            "%1 notas se fusionaron con una categoría que ya existía.",
        "An analysis is running on this link. Try again when it finishes.":
            "Hay un análisis corriendo sobre este link. Probá de nuevo cuando termine.",
        "The vault could not be written. Check that the folder exists and "
        "that you can write to it.":
            "No se pudo escribir en el vault. Revisá que la carpeta exista y "
            "que puedas escribir en ella.",
        "The settings could not be saved. Check that the config folder exists "
        "and that you can write to it.":
            "No se pudieron guardar los ajustes. Revisá que la carpeta de "
            "configuración exista y que puedas escribir en ella.",
        "Re-run the analysis? The title, summary, points, category, tags and "
        "mentions are replaced by the new answer.":
            "¿Reprocesar? El título, el resumen, los puntos, la categoría, las "
            "etiquetas y las menciones se reemplazan por la respuesta nueva.",
        "Mentions": "Menciones",
        "search": "búsqueda",
        "Remove": "Quitar",
        "%1 notes moved, %2 could not be written. "
        "Check the folder and try again.":
            "Se movieron %1 notas; %2 no se pudieron escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "1 note moved, %2 could not be written. "
        "Check the folder and try again.":
            "Se movió 1 nota; %2 no se pudieron escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "%1 notes moved, 1 could not be written. "
        "Check the folder and try again.":
            "Se movieron %1 notas; 1 no se pudo escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "1 note moved, 1 could not be written. "
        "Check the folder and try again.":
            "Se movió 1 nota; 1 no se pudo escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "Saved, but the indexes could not be rebuilt. Run "
        "`oknowledge reindex` once the folder is writable again.":
            "Guardado, pero no se pudieron rehacer los índices. Corré "
            "`oknowledge reindex` cuando la carpeta vuelva a ser escribible.",
        "The note was moved to the trash folder inside your vault, but the "
        "indexes could not be rebuilt. Run `oknowledge reindex` once the "
        "folder is writable again.":
            "La nota se movió a la carpeta trash de tu vault, pero no se "
            "pudieron rehacer los índices. Corré `oknowledge reindex` cuando "
            "la carpeta vuelva a ser escribible.",
        "The settings were saved, but the interface language is shared with "
        "my other plugins and that file could not be written.":
            "Los ajustes se guardaron, pero el idioma de la interfaz es "
            "compartido con mis otros plugins y ese archivo no se pudo escribir.",
        "Renaming into a category that already exists merges the two.":
            "Si el nombre nuevo ya existe, las dos categorías se fusionan.",
        "Move this note to the trash folder?":
            "¿Mover esta nota a la carpeta trash?",
        "Saving rewrites %1 from scratch: your comments, your formatting and "
        "any key oknowledge does not read are not kept. The file it replaces "
        "is copied to config.toml.bak first.":
            "Guardar reescribe %1 de cero: tus comentarios, tu formato y "
            "cualquier clave que oknowledge no lea no se conservan. El archivo "
            "que reemplaza se copia antes a config.toml.bak.",
        "Priority runs top to bottom. An engine that is not checked is not used. "
        "To change the order, edit the file by hand.":
            "La prioridad va de arriba hacia abajo. El motor que no esté tildado "
            "no se usa. Para cambiar el orden, editá el archivo a mano.",
        "The API key is not written here: it goes in config.toml as key_env, "
        "or in the environment variable that field names.":
            "La API key no se escribe acá: va en config.toml como key_env, "
            "o en la variable de entorno que ese campo nombre.",
        "Shared with my other Omarchy plugins, so this changes all of them at once.":
            "Es compartido con mis otros plugins de Omarchy: los cambia a todos juntos.",
        "Mentions of a video": "Menciones de un video",
        "Tools and companies": "Herramientas y empresas",
        "Everything named": "Todo lo nombrado",
        "Only what it discusses": "Sólo lo que discute",
    },
}


def ui_language(path: Path | None = None) -> str:
    target = Path(path) if path else SHARED_FILE
    try:
        value = json.loads(target.read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError, RecursionError):
        return "en"
    if not isinstance(value, str):
        return "en"
    primary = value.strip().lower().replace("_", "-").split("-")[0]   # "es-AR" -> "es"
    return primary if primary in LANGUAGES else "en"


def set_ui_language(language: str, path: Path | None = None) -> Path:
    """Write the shared preference, and say where it went.

    The file is not ours: every Omarchy plugin of mine reads and writes it, so
    this reads what is there, changes the one key we own and writes the whole
    object back. Writing {"language": ...} wholesale would quietly destroy
    whatever another plugin keeps there. A file that is missing, unreadable or
    not a JSON object starts from an empty object rather than failing: the
    preference is worth more than whatever could not be parsed.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    target = Path(path) if path else SHARED_FILE
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        existing = None
    data = dict(existing) if isinstance(existing, dict) else {}
    data["language"] = language
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return target


def translator(language: str):
    table = STRINGS.get(language, {})

    def t(text: str, *args) -> str:
        out = table.get(text, text)

        def value(match: re.Match) -> str:
            n = int(match.group(1))
            if n == 0 or n > len(args):
                return match.group(0)        # not a marker we were given
            return str(args[n - 1])

        # One pass, like plugin/I18n.js: a loop would re-scan its own output
        # and substitute a marker that arrived inside an argument.
        return re.sub(r"%(\d+)", value, out)

    return t
