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


@pytest.mark.parametrize("raw", [
    '```json\n{"a": 1}\n```',                          # fence with a language tag
    '```\n{"a": 1}\n```',                              # bare fence, no tag
    '```JSON\n{"a": 1}\n```',                          # upper-case tag
    'Acá está la ficha: {"a": 1}',                     # preamble on the same line
    'Claro, te paso la ficha.\n\n{"a": 1}',            # preamble sentence
    '{"a": 1}\n\nEspero que te sirva.',                # chatter after
    '{"a": 1}\n\nNota: usé {llaves} y {otra}.',        # chatter after, with braces
    'Mirá {esto}: {"a": 1}',                           # braces in the preamble
    'Aquí va:\n```json\n{"a": 1}\n```\nSi querés lo ajusto {así}.',
    '```json\n{"a": 1}',                               # fence never closed
    '﻿  {"a": 1}  ',                              # BOM and whitespace
])
def test_realistic_wrappers_around_the_object_are_all_understood(raw):
    assert extract_json(raw) == {"a": 1}


def test_braces_inside_string_values_do_not_confuse_it():
    raw = ('Va:\n```json\n{"summary": "usa {llaves} y \\"}\\" dentro", '
           '"nested": {"k": ["}", "{"]}}\n```\nListo {x}')
    assert extract_json(raw) == {
        "summary": 'usa {llaves} y "}" dentro',
        "nested": {"k": ["}", "{"]},
    }


def test_a_fence_with_nested_objects_is_understood():
    raw = '```json\n{"a": {"b": {"c": 1}}}\n```'
    assert extract_json(raw) == {"a": {"b": {"c": 1}}}


def test_a_json_array_or_scalar_is_not_an_object():
    with pytest.raises(AnalysisError):
        extract_json('[1, 2, 3]')
    with pytest.raises(AnalysisError):
        extract_json('"hola"')


def test_truncated_json_raises():
    with pytest.raises(AnalysisError):
        extract_json('{"title": "x", "summary": "se cortó')


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


def test_page_text_that_looks_like_a_placeholder_is_left_alone():
    prompt = render_prompt("mirá {{CATEGORIES}} y {{URL}}", META, ["Redes"], "es")
    assert prompt.count("- Redes") == 1
    assert "mirá {{CATEGORIES}} y {{URL}}" in prompt


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


def test_a_fenced_answer_with_chatter_goes_through_analyze():
    raw = "Claro:\n```json\n" + json.dumps(GOOD) + "\n```\nSaludos {fin}"
    engine = FakeEngine([raw])
    assert analyze(engine, "texto", META, [], "es").title == "WireGuard vs OpenVPN"
    assert len(engine.prompts) == 1


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


@pytest.mark.parametrize("field,value", [
    ("points", "una sola cadena"),
    ("points", None),
    ("tags", "vpn, redes"),
    ("tags", None),
    ("summary", None),
    ("summary", ["no", "es", "texto"]),
    ("title", None),
    ("category", ["redes"]),
])
def test_fields_of_the_wrong_type_are_rejected_not_garbled(field, value):
    bad = json.dumps(dict(GOOD, **{field: value}))
    engine = FakeEngine([bad, bad])
    with pytest.raises(AnalysisError):
        analyze(engine, "texto", META, [], "es")


def test_an_empty_title_falls_back_to_the_detected_one():
    engine = FakeEngine([json.dumps(dict(GOOD, title="  "))])
    assert analyze(engine, "texto", META, [], "es").title == META["title"]


def test_an_empty_category_falls_back_instead_of_breaking():
    data = dict(GOOD, category="   ")
    engine = FakeEngine([json.dumps(data)])
    assert analyze(engine, "texto", META, [], "es").category == "Sin clasificar"


def test_text_longer_than_the_limit_is_cut_from_the_end():
    baseline = render_prompt("", META, [], "es", limit=1000).count("x")
    prompt = render_prompt("x" * 100_000, META, [], "es", limit=1000)
    assert prompt.count("x") == baseline + 1000


def test_the_fake_engine_replays_replies_records_prompts_and_raises_exceptions():
    from oknowledge.ai.base import EngineError
    engine = FakeEngine(["uno", EngineError("boom")])
    assert engine.complete("p1") == "uno"
    with pytest.raises(EngineError):
        engine.complete("p2")
    with pytest.raises(EngineError):
        engine.complete("p3")
    assert engine.prompts == ["p1", "p2", "p3"]


def _example_from_prompt() -> str:
    prompt = render_prompt("t", META, [], "es")
    return prompt[prompt.index("{"):prompt.index("}\n") + 1]


def test_an_echoed_schema_example_before_the_real_answer_loses_to_the_answer():
    example = _example_from_prompt()
    assert set(json.loads(example)) == set(GOOD)  # the echo really is complete
    raw = f"Claro, la forma es:\n{example}\nY acá está la ficha:\n```json\n{json.dumps(GOOD)}\n```"
    assert extract_json(raw) == GOOD
    result = analyze(FakeEngine([raw]), "texto", META, [], "es")
    assert result.title == "WireGuard vs OpenVPN" and result.category == "redes"


def test_trailing_json_without_the_required_keys_does_not_beat_the_answer():
    raw = json.dumps(GOOD) + '\n\nSi querés, config: {"lang": "es", "n": 3}'
    assert extract_json(raw) == GOOD


def test_two_complete_answers_in_a_row_the_last_one_wins():
    # Deliberate: a model that corrects or retries itself ends with its final word.
    first, second = dict(GOOD, title="Primero"), dict(GOOD, title="Segundo")
    raw = f"{json.dumps(first)}\nMejor así:\n{json.dumps(second)}"
    assert extract_json(raw)["title"] == "Segundo"


def test_objects_nested_inside_the_answer_are_not_candidates():
    data = dict(GOOD, extra={"title": "x", "summary": "x", "points": [], "category": "x", "tags": []})
    assert extract_json(json.dumps(data)) == data
