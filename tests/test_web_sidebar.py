"""The sidebar that replaces the header on every page."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, category="Redes"):
    return Note(id=id, url=f"https://e.com/{id}", title=id, category=category, tags=[],
                type="article", source="e.com", saved="2026-10-03", summary="s")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for i in range(3):
        write_note(cfg, note(f"a{i}"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def sidebar(body):
    return re.search(r'<aside class="sidebar".*?</aside>', body, re.S).group(0)


@pytest.mark.parametrize("path", ["/settings", "/ocio", "/ideas", "/import",
                                  "/categories", "/retry", "/nothing-here"])
def test_every_page_has_the_sidebar(client, path):
    body = client.get(path).text
    side = sidebar(body)
    assert 'href="/"' in side and 'href="/ocio"' in side and 'href="/ideas"' in side
    assert 'href="/settings"' in side and 'href="/categories"' not in side and 'href="/retry"' not in side


def test_the_old_header_is_gone(client):
    body = client.get("/settings").text
    assert "<header>" not in body
    assert 'action="/search"' not in body
    assert "paste-form" not in body


def test_the_sections_carry_their_counts(client):
    side = sidebar(client.get("/settings").text)
    assert re.search(r'href="/"[^>]*>.*?<b class="count[^"]*">3</b>', side, re.S)


@pytest.mark.parametrize("path,active", [("/ocio", "/ocio"), ("/ideas", "/ideas")])
def test_the_section_you_are_in_is_marked(client, path, active):
    side = sidebar(client.get(path).text)
    assert f'href="{active}" class="section on"' in side


def test_a_page_outside_the_sections_marks_none(client):
    assert "section on" not in sidebar(client.get("/settings").text)


def test_the_legacy_pages_scroll_in_their_own_column(client):
    body = client.get("/settings").text
    assert '<div class="app legacy">' in body
    assert '<div class="legacy-main">' in body


def test_the_counts_follow_the_vault_on_every_page(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    client = TestClient(create_app(cfg))
    client.get("/settings")
    from oknowledge.vault import note_path
    card = note("c1")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = note("i1")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    side = sidebar(client.get("/settings").text)
    assert re.search(r'href="/ocio"[^>]*>.*?<b class="count[^"]*">1</b>', side, re.S)
    assert re.search(r'href="/ideas"[^>]*>.*?<b class="count[^"]*">1</b>', side, re.S)


# --- the DATES group (docs/2026-10-07-linea-de-tiempo-design.md, in the
#     sidebar now that the right-hand strip is gone) -------------------------

def dated(id, saved, category="Redes"):
    return Note(id=id, url=f"https://e.com/{id}", title=id, category=category, tags=[],
                type="article", source="e.com", saved=saved, summary="s")


@pytest.fixture
def years(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, saved, category in [("a", "2026-10-04", "Redes"), ("b", "2026-09-30", "Redes"),
                                ("c", "2021-11-02", "Salud"), ("d", "2021-03-01", "Salud"),
                                ("e", "nada", "Redes")]:
        write_note(cfg, dated(id, saved, category), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_library_lists_its_years_with_what_they_hold(years):
    side = sidebar(years.get("/").text)
    assert "DATES" in side
    assert '/?when=2026' in side and '/?when=2021' in side
    assert side.index("?when=2026") < side.index("?when=2021")   # newest first


def test_a_year_that_is_open_shows_its_months_and_nothing_elses(years):
    side = sidebar(years.get("/?when=2021").text)
    assert "?when=2021-11" in side and "?when=2021-03" in side
    assert "Nov" in side and "Mar" in side
    assert "?when=2026-10" not in side


def test_without_a_year_open_no_month_is_listed(years):
    assert "?when=2021-11" not in sidebar(years.get("/").text)


def test_the_month_is_marked_and_its_year_is_the_way_back_to_the_whole_year(years):
    side = sidebar(years.get("/?when=2021-11").text)
    assert re.search(r'href="/\?when=2021-11"[^>]*class="filter month on"', side)
    assert re.search(r'href="/\?when=2021"[^>]*class="filter"', side)


def test_the_notes_nobody_can_date_are_a_period_of_their_own(years):
    side = sidebar(years.get("/").text)
    assert "?when=undated" in side and "Undated" in side


def test_a_year_with_nothing_of_what_you_are_looking_at_is_not_a_link(years):
    # Shown and dimmed, not removed: the shape of time must not change from
    # page to page.
    side = sidebar(years.get("/?cat=Salud").text)
    assert "?cat=Salud&amp;when=2021" in side
    assert "when=2026" not in side and 'class="filter off"' in side


def test_a_year_keeps_the_category_and_a_category_keeps_the_year(years):
    assert "?cat=Redes&amp;when=2026" in sidebar(years.get("/?cat=Redes").text)
    assert "?cat=Redes&amp;when=2021" in sidebar(years.get("/?when=2021").text)


def test_the_groups_own_all_clears_the_period_and_leaves_the_rest(years):
    side = sidebar(years.get("/?cat=Salud&when=2021").text)
    assert '"/?cat=Salud"' in side


def test_a_search_has_no_dates_beside_it(years):
    # That list is ordered by how well it matches, not by time.
    assert "DATES" not in sidebar(years.get("/?q=nada").text)


def test_a_period_this_library_does_not_have_shows_nothing_found(years):
    body = years.get("/?when=1999").text
    assert "There is nothing in 1999" in body and ">a</" not in body


def test_the_phone_gets_the_years_as_a_chip_row_of_their_own(years):
    row = re.search(r'<nav class="chip-row chip-dates".*?</nav>', years.get("/").text, re.S).group(0)
    assert "?when=2026" in row and "?when=2021" in row and "?when=undated" in row
