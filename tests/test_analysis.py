import json

import pytest

from oknowledge.ai.base import (
    DEFAULT_LIMIT, TRUNCATION_MARKER, Analysis, AnalysisError, EngineError, analyze,
    canonical_category, extract_json, normalize_tags, render_prompt, retry_suffix,
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
    first, second = engine.prompts
    reason = "the answer had no JSON object in it"
    assert second.startswith(first)
    assert second.endswith(retry_suffix("es", reason))
    assert reason in second  # the retry says what was wrong, not a generic "invalid JSON"


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
    engine = FakeEngine(["uno", EngineError("boom")])
    assert engine.complete("p1") == "uno"
    with pytest.raises(EngineError):
        engine.complete("p2")
    with pytest.raises(EngineError):
        engine.complete("p3")
    assert engine.prompts == ["p1", "p2", "p3"]


def _example_from_prompt() -> str:
    prompt = render_prompt("t", META, [], "es")
    example, _ = json.JSONDecoder().raw_decode(prompt, prompt.index("{"))
    return json.dumps(example, ensure_ascii=False)


def test_an_echoed_schema_example_before_the_real_answer_loses_to_the_answer():
    example = _example_from_prompt()
    assert set(json.loads(example)) == set(GOOD)  # the echo really is complete
    assert extract_json(example) == json.loads(example)
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


# --- round 3: failure paths of real small-model output -----------------------


def test_a_literal_newline_inside_a_string_value_is_understood():
    raw = '{"summary": "primera línea\nsegunda línea", "b": 1}'  # a real newline, not \\n
    assert "\n" in raw
    assert extract_json(raw) == {"summary": "primera línea\nsegunda línea", "b": 1}


def test_a_multiline_summary_survives_analyze_on_the_first_attempt():
    raw = FakeEngine.answer().replace("A summary of what the page says.", "linea uno\nlinea dos")
    raw = raw.replace("\\n", "\n")  # a literal newline, as the model would write it
    engine = FakeEngine([raw])
    assert analyze(engine, "t", META, [], "es").summary == "linea uno\nlinea dos"
    assert len(engine.prompts) == 1


def test_every_string_in_the_prompt_example_is_a_placeholder():
    example = json.loads(_example_from_prompt())
    strings = [example["title"], example["summary"], example["category"],
               *example["points"], *example["tags"]]
    assert all(v.startswith("<") and v.endswith(">") for v in strings)


def _rejected(reply, replies=None):
    engine = FakeEngine(replies or [reply, reply])
    with pytest.raises(AnalysisError):
        analyze(engine, "t", META, [], "es")


def test_an_echoed_example_alone_is_rejected_not_stored():
    _rejected(_example_from_prompt())


def test_an_echo_followed_by_a_truncated_answer_is_rejected():
    _rejected(_example_from_prompt() + '\nAhora sí:\n{"title": "WireGuard", "summary": "se cor')


def test_an_echo_introduced_as_the_format_is_rejected():
    _rejected("Acá está el formato: " + _example_from_prompt())


def test_an_echo_is_retried_and_the_real_answer_is_then_accepted():
    engine = FakeEngine([_example_from_prompt(), json.dumps(GOOD)])
    assert analyze(engine, "t", META, [], "es").title == "WireGuard vs OpenVPN"
    assert len(engine.prompts) == 2


def test_tags_that_are_not_text_are_dropped_not_stringified():
    assert normalize_tags(["vpn", None, {"a": 1}, 3, ["x"]]) == ["vpn"]


def test_placeholder_tags_are_dropped():
    assert normalize_tags(["<una etiqueta>", "ok"]) == ["ok"]


def test_points_that_are_not_text_are_dropped_not_stringified():
    data = dict(GOOD, points=[{"point": "ficha"}, None, 7, "real", "<una idea>"])
    result = analyze(FakeEngine([json.dumps(data)]), "t", META, [], "es")
    assert result.points == ["real"]


def test_the_prompt_says_when_the_text_was_cut_and_only_then():
    cut = render_prompt("y" * (DEFAULT_LIMIT + 1), META, [], "es")
    whole = render_prompt("y" * DEFAULT_LIMIT, META, [], "es")
    assert TRUNCATION_MARKER in cut
    assert TRUNCATION_MARKER not in whole
    assert cut.index("y" * DEFAULT_LIMIT) < cut.index(TRUNCATION_MARKER)
    assert "cortado" in whole  # the instruction itself is always there


def test_a_non_ascii_category_that_is_already_known_is_kept():
    assert canonical_category("日本料理", ["日本料理"]) == "日本料理"
    assert canonical_category("日本料理", []) == "日本料理"
    assert canonical_category("ЭКОНОМИКА", ["Экономика"]) == "Экономика"


def test_a_category_differing_only_by_surrounding_whitespace_matches():
    assert canonical_category("  Redes\t", ["Redes"]) == "Redes"
    assert canonical_category("Redes", ["Redes "]) == "Redes "


def test_category_path_separators_become_spaces():
    assert canonical_category("../Redes/VPN", []) == "Redes VPN"
    assert canonical_category("a\\b", []) == "a b"


def test_a_category_with_an_embedded_newline_or_control_character_is_one_line():
    assert canonical_category("Redes\ny\x00VPN", []) == "Redes y VPN"


def test_collapsed_whitespace_lets_a_category_match_a_known_one():
    assert canonical_category("Redes   y   VPN", ["Redes y VPN"]) == "Redes y VPN"


@pytest.mark.parametrize("bad", [".", "..", "...", " / ", "\n"])
def test_degenerate_categories_fall_back(bad):
    assert canonical_category(bad, []) == "Sin clasificar"


def test_a_listed_category_keeps_only_its_first_segment():
    assert canonical_category("Redes, Seguridad", []) == "Redes"
    assert canonical_category("Redes; Seguridad", []) == "Redes"
    assert canonical_category("Redes, Seguridad", ["Redes"]) == "Redes"


def test_a_known_category_containing_a_comma_still_matches_itself():
    assert canonical_category("Redes, Seguridad", ["Redes, Seguridad"]) == "Redes, Seguridad"


def test_a_very_long_category_is_capped():
    assert len(canonical_category("a" * 500, [])) <= 80


def test_the_fallback_category_follows_the_language():
    assert canonical_category("", [], "es") == "Sin clasificar"
    assert canonical_category("", [], "en") == "Unclassified"
    assert canonical_category("", [], "fr") == "Unclassified"
    engine = FakeEngine([json.dumps(dict(GOOD, category=" "))])
    assert analyze(engine, "t", META, [], "en").category == "Unclassified"


def test_programming_symbols_survive_in_tags():
    assert normalize_tags(["C++", "C#", "F#", ".NET", "C"]) == ["cpp", "csharp", "fsharp", "dotnet", "c"]
    assert normalize_tags(["C++ templates"]) == ["cpp-templates"]


def test_non_latin_tags_survive():
    assert normalize_tags(["日本語", "Привет мир", "がっこう"]) == ["日本語", "привет-мир", "がっこう"]


def test_tag_shapes_hash_spaces_duplicates_and_length():
    assert normalize_tags(["#python"]) == ["python"]
    assert normalize_tags(["machine learning"]) == ["machine-learning"]
    assert normalize_tags(["Año", "ano", "ANO"]) == ["ano"]
    assert normalize_tags(["x" * 100]) == ["x" * 40]
    assert normalize_tags(["###", "..."]) == []


def test_an_answer_wrapped_in_a_single_key_is_unwrapped():
    raw = json.dumps({"ficha": GOOD})
    assert extract_json(raw) == GOOD
    assert analyze(FakeEngine([raw]), "t", META, [], "es").title == "WireGuard vs OpenVPN"


def test_without_known_categories_the_prompt_says_so_and_lists_no_bullet():
    prompt = render_prompt("t", META, [], "es")
    assert "todavía no hay ninguna" in prompt
    assert "- (" not in prompt and "estas ya existen" not in prompt
    assert "{{" not in prompt
    with_known = render_prompt("t", META, ["Redes"], "es")
    assert "estas ya existen" in with_known and "todavía no hay ninguna" not in with_known


def test_the_known_categories_are_capped_keeping_the_caller_order():
    known = [f"cat{i:03d}" for i in range(200)]
    prompt = render_prompt("t", META, known, "es")
    assert "- cat059" in prompt and "- cat060" not in prompt
    # the cap only shapes the prompt: an existing category past it still wins
    engine = FakeEngine([json.dumps(dict(GOOD, category="CAT150"))])
    assert analyze(engine, "t", META, known, "es").category == "cat150"


def test_the_page_text_is_fenced_and_the_reminder_comes_after_it():
    prompt = render_prompt("TEXTO-DE-LA-PAGINA", META, [], "en")
    start, end = prompt.index("<<<CONTENIDO\n"), prompt.index("\nCONTENIDO>>>")
    assert start < prompt.index("TEXTO-DE-LA-PAGINA") < end
    assert "inglés" in prompt[end:]  # language reminder after the content


def test_the_retry_message_is_localized_and_names_the_failure():
    assert "sólo" in retry_suffix("es", "x") and "ONLY" not in retry_suffix("es", "x")
    assert "only" in retry_suffix("en", "x")
    engine = FakeEngine([json.dumps({"title": "x"}), json.dumps(GOOD)])
    analyze(engine, "t", META, [], "es")
    assert "missing: summary, points, category, tags" in engine.prompts[1]


def test_the_final_error_keeps_its_cause():
    engine = FakeEngine(["no", json.dumps({"title": "x"})])
    with pytest.raises(AnalysisError) as info:
        analyze(engine, "t", META, [], "es")
    assert isinstance(info.value.__cause__, AnalysisError)
    assert "missing" in str(info.value)


def test_title_falls_back_to_the_detected_title_then_to_the_url():
    empty = json.dumps(dict(GOOD, title=""))
    assert analyze(FakeEngine([empty]), "t", META, [], "es").title == META["title"]
    bare = {"url": "https://e.com/x", "title": None}
    assert analyze(FakeEngine([empty]), "t", bare, [], "es").title == "https://e.com/x"


# --- the fake engine ----------------------------------------------------------


def test_a_fake_reply_can_be_a_callable_of_the_prompt():
    engine = FakeEngine([lambda p: FakeEngine.answer(title="uno" if "AAA" in p else "otro")])
    assert json.loads(engine.complete("AAA"))["title"] == "uno"


def test_a_fake_that_is_a_callable_answers_every_prompt_in_any_order():
    engine = FakeEngine(lambda p: FakeEngine.answer(title=p))
    assert [json.loads(engine.complete(p))["title"] for p in ("b", "a", "b")] == ["b", "a", "b"]


def test_a_callable_reply_may_return_an_exception_to_raise():
    engine = FakeEngine([lambda p: EngineError("boom")])
    with pytest.raises(EngineError):
        engine.complete("p")


def test_a_fake_rejects_an_exception_class_and_non_str_replies_clearly():
    with pytest.raises(TypeError, match="class EngineError"):
        FakeEngine([EngineError]).complete("p")
    with pytest.raises(TypeError, match="NoneType"):
        FakeEngine([None]).complete("p")
    with pytest.raises(TypeError, match="NoneType"):
        FakeEngine([lambda p: None]).complete("p")


def test_the_fake_answer_helper_is_valid_and_overridable():
    assert analyze(FakeEngine([FakeEngine.answer()]), "t", META, [], "es").category == "General"
    custom = FakeEngine.answer(category="Redes", tags=["x"])
    assert analyze(FakeEngine([custom]), "t", META, [], "es").tags == ["x"]
    assert json.loads(FakeEngine.answer(points=None))["points"] is None


# --- what the model invents, the web can edit (F11) -------------------------
# _clean_category stripped leading dots but not trailing ones, and left
# : * ? " < > | alone, so the AI could store "Misc." or "Q&A: tips" -- names
# vault.clean_category() then refuses, because they are not fixed points of
# the index file name. The product generated categories you could not edit in
# the product.

NASTY = [
    "Misc.",
    "Varios...",
    "Q&A: tips",
    "¿Qué leer?",
    'Libros "buenos"',
    "Ciencia ficción*",
    "a|b",
    "<html>",
    "C:\\Users\\fer",
    "../Redes/VPN",
    " . ",
    "a" * 200 + ".",
    "x" * 79 + " y.",
    "Notas…",
    "Redes\ny\x00VPN",
]


def test_a_category_the_model_invents_is_one_the_web_accepts():
    """The property, over every shape I could think of: canonical_category's
    answer always survives vault.clean_category() unchanged."""
    from oknowledge.vault import clean_category

    for raw in NASTY:
        out = canonical_category(raw, [])
        assert clean_category(out) == out, f"{raw!r} became {out!r}, which the web refuses"


def test_the_trailing_dot_the_review_found():
    assert canonical_category("Misc.", []) == "Misc"
    assert canonical_category("Varios...", []) == "Varios"


def test_the_characters_a_file_name_cannot_hold_become_spaces():
    assert canonical_category("Q&A: tips", []) == "Q&A tips"
    assert canonical_category("¿Qué leer?", []) == "¿Qué leer"
    assert canonical_category("a|b", []) == "a b"


def test_truncation_does_not_leave_a_name_the_web_refuses():
    """The strip has to come after the cut, not before it."""
    out = canonical_category("x" * 79 + ".tail", [])
    assert len(out) <= 80
    assert not out.endswith(".")


def test_the_web_refuses_every_character_the_index_name_replaces():
    """Both sides read UNSAFE_IN_A_NAME. This is what makes that one list
    load-bearing: drop a character from either reader and the web starts
    accepting a category whose index file would be called something else."""
    from oknowledge.ai.base import UNSAFE_IN_A_NAME
    from oknowledge.vault import clean_category

    for char in UNSAFE_IN_A_NAME:
        assert clean_category(f"a{char}b") is None, f"{char!r} is accepted as a category"
        assert char not in canonical_category(f"a{char}b", [])


def test_a_category_already_in_the_vault_is_still_returned_as_it_is():
    """Deliberately not cleaned: matching a known category must never rename
    what the user already has. Only invented names are constrained."""
    assert canonical_category("Redes", ["Redes "]) == "Redes "
    assert canonical_category("misc.", ["Misc."]) == "Misc."
