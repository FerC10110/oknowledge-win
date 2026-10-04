"""The interface language: English by default, Spanish opt-in.

The preference is not this project's: it lives in the shared Omarchy file that
all my plugins read. The English text is the key, so a missing translation
degrades to English and nothing breaks. This is a separate axis from the
language the AI writes summaries in (`[ai] language`).
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
        "1 note could not be read and is not shown (%1)":
            "1 nota no se pudo leer y no se muestra (%1)",
        "%1 notes could not be read and are not shown (%2)":
            "%1 notas no se pudieron leer y no se muestran (%2)",
        "The vault could not be read": "No se pudo leer el vault",
        "Check that the folder exists, is mounted and is readable.":
            "Revisá que la carpeta exista, esté montada y se pueda leer.",
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
