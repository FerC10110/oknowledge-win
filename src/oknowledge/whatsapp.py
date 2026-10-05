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
    "﻿": "", " ": " ", " ": " ", " ": " ",
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
