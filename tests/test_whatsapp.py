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
21/7/2019, 13:50 - Fer: "Easy DevOps" by George Seif https://link.medium.com/JfoglQ1zvY
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
        "‎18/7/2019, 11:36 - Fer: https://e.com/x\n")

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
