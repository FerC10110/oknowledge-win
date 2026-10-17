"""The dates axis: the years and the months the library holds, and the
`when` filter the sidebar's DATES group drives.

Brought back from docs/2026-10-07-linea-de-tiempo-design.md, which the
redesign's first delivery dropped along with the old right-hand strip.
"""

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import write_note
from oknowledge.web.index import UNDATED, Library, period_of, tally


def note(id, saved="2026-10-04", category="Redes", tags=(), collections=()):
    return Note(id=id, url=f"https://e.com/{id}", title=id, category=category,
                tags=list(tags), type="article", source="e.com", saved=saved,
                summary="s", collections=list(collections))


DATES = {"a": "2026-10-04", "b": "2026-09-30", "c": "2021-11-02",
         "d": "2021-11-20", "e": "2021-03-01", "f": "roto"}


@pytest.fixture
def library(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, saved in DATES.items():
        write_note(cfg, note(id, saved=saved), "es")
    return Library(cfg)


# --- what period a note belongs to -----------------------------------------

@pytest.mark.parametrize("size, expected", [(4, "2021"), (7, "2021-11")])
def test_a_date_gives_its_year_and_its_month(size, expected):
    assert period_of("2021-11-02", size) == expected


@pytest.mark.parametrize("saved", ["", "roto", "2021-13-02", "2021-11", "ayer"])
def test_a_date_nobody_can_read_is_undated_whatever_the_size(saved):
    # Never a year it is not from: `saved` is text the user can edit by hand.
    assert period_of(saved) == period_of(saved, 7) == UNDATED


# --- the index --------------------------------------------------------------

def test_the_years_come_newest_first_with_the_undated_last(library):
    assert list(library.years()) == ["2026", "2021", UNDATED]
    assert library.years() == {"2026": 2, "2021": 3, UNDATED: 1}


def test_the_months_come_newest_first_and_leave_the_undated_out(library):
    assert library.months() == {"2026-10": 1, "2026-09": 1,
                                "2021-11": 2, "2021-03": 1}
    assert list(library.months()) == ["2026-10", "2026-09", "2021-11", "2021-03"]


def test_the_periods_are_the_years_and_the_months(library):
    assert library.periods() == {"2026", "2021", UNDATED,
                                 "2026-10", "2026-09", "2021-11", "2021-03"}


def test_a_vault_that_cannot_be_read_holds_no_period(tmp_path):
    library = Library(Config(vault=tmp_path / "gone"))
    assert library.error is not None
    assert library.years() == {} and library.months() == {} and library.periods() == set()


# --- the filter -------------------------------------------------------------

def test_a_year_brings_the_whole_year(library):
    assert sorted(n.id for n in library.filter(when="2021")) == ["c", "d", "e"]


def test_a_month_brings_only_that_month(library):
    assert sorted(n.id for n in library.filter(when="2021-11")) == ["c", "d"]


def test_undated_brings_the_notes_nobody_can_date(library):
    assert [n.id for n in library.filter(when=UNDATED)] == ["f"]


@pytest.mark.parametrize("when", ["2021-1", "2017", "hola", "2021-11-02"])
def test_a_when_that_names_no_period_of_this_library_brings_nothing(library, when):
    # Not a prefix match and not ignored: "2021-1" would eat October,
    # November and December, and a filter dropped in silence shows
    # everything as if that were the answer.
    assert library.filter(when=when) == []


def test_a_period_crosses_with_the_other_filters(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("x", saved="2021-11-02", category="Salud"), "es")
    write_note(cfg, note("y", saved="2021-11-03", category="Redes"), "es")
    write_note(cfg, note("z", saved="2026-10-04", category="Salud"), "es")
    library = Library(cfg)
    assert [n.id for n in library.filter(category="Salud", when="2021")] == ["x"]


# --- the counters the group shows -------------------------------------------

def test_the_tally_counts_each_year_and_each_month_of_what_it_is_given():
    notes = [note("a", saved="2021-11-02"), note("b", saved="2021-11-20"),
             note("c", saved="2021-03-01")]
    assert tally(notes) == {"2021": 3, "2021-11": 2, "2021-03": 1}


def test_the_tally_puts_an_unreadable_date_in_no_month():
    assert tally([note("a", saved="roto")]) == {UNDATED: 1}


# --- what the sidebar's DATES group is given ---------------------------------

def test_the_group_lists_every_year_of_the_library_newest_first(library):
    from oknowledge.web.library_view import View, date_groups
    shown = date_groups(library, View())
    assert shown["years"] == [("2026", 2), ("2021", 3), (UNDATED, 1)]
    assert shown["when_total"] == 6


def test_the_months_are_the_open_years_own_with_their_name(library):
    from oknowledge.web.library_view import View, date_groups
    assert date_groups(library, View(when="2021"))["months"] == [
        ("2021-11", "Nov", 2), ("2021-03", "Mar", 1)]


@pytest.mark.parametrize("when", ["", UNDATED])
def test_without_a_year_open_there_are_no_months(library, when):
    from oknowledge.web.library_view import View, date_groups
    assert date_groups(library, View(when=when))["months"] == []


def test_a_month_of_the_open_year_opens_the_same_year(library):
    from oknowledge.web.library_view import View, date_groups
    assert date_groups(library, View(when="2021-11"))["months"] == [
        ("2021-11", "Nov", 2), ("2021-03", "Mar", 1)]


def test_the_counters_are_over_what_the_other_filters_left(tmp_path):
    from oknowledge.web.library_view import View, date_groups
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("x", saved="2021-11-02", category="Salud"), "es")
    write_note(cfg, note("y", saved="2026-10-04", category="Redes"), "es")
    library = Library(cfg)
    shown = date_groups(library, View(cat="Salud"))
    # The shape of time does not change with the filter: both years stay,
    # and the one that holds nothing of this category is a 0, not a gap.
    assert shown["years"] == [("2026", 0), ("2021", 1)]
    assert shown["when_total"] == 1


def test_the_period_itself_does_not_count_against_the_group(library):
    from oknowledge.web.library_view import View, date_groups
    # Otherwise the year you opened would be the only one with a number.
    assert date_groups(library, View(when="2021"))["years"] == [
        ("2026", 2), ("2021", 3), (UNDATED, 1)]
