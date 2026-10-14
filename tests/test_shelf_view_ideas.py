"""The ideas list as one URL describes it (spec §2): pure, no app."""

import pytest

from oknowledge.ideas import new_idea
from oknowledge.web.library_view import CHUNK
from oknowledge.web.shelf_view import IdeaView, choose_ideas, idea_filters


def idea(n, state="pending", text="", title=None, tags=(), saved=None):
    note = new_idea(text or f"Texto {n}.", f"Idea {n}" if title is None else title,
                    saved or f"2026-10-{n:02d}", f"2026-10-{n:02d}T00:00:00.000001+00:00")
    note.state, note.tags = state, list(tags)
    return note


def test_an_unknown_state_and_layout_are_the_usual_view():
    view = IdeaView.from_query({"estado": "archived", "vista": "x", "hasta": "7"})
    assert (view.estado, view.vista, view.hasta) == ("", "tarjetas", CHUNK)


def test_the_url_leaves_out_the_defaults():
    assert IdeaView().url() == "/ideas"
    assert IdeaView(estado="doing", vista="lista").url(q="vpn") == "/ideas?estado=doing&q=vpn&vista=lista"
    assert IdeaView(q="vpn").url("/ideas/lista", desde=60) == "/ideas/lista?q=vpn&desde=60"


def test_opening_an_idea_carries_the_way_back():
    assert IdeaView(estado="doing").open("abc") == "/ideas/abc?back=%2Fideas%3Festado%3Ddoing"
    assert IdeaView().open("abc") == "/ideas/abc"


def test_the_label():
    t = lambda text, *a: text
    assert IdeaView().label(t) == "Ideas"
    assert IdeaView(estado="doing").label(t) == "under way"
    assert IdeaView(q="vpn").label(t) == "Results"


def test_newest_first_and_the_dropped_out_of_all():
    notes = [idea(1), idea(3, "dropped"), idea(2, "done")]
    assert [n.title for n in choose_ideas(notes, IdeaView())] == ["Idea 2", "Idea 1"]


def test_a_state_shows_only_its_ideas_dropped_too():
    notes = [idea(1), idea(3, "dropped")]
    assert [n.title for n in choose_ideas(notes, IdeaView(estado="dropped"))] == ["Idea 3"]


def test_the_search_reads_title_text_and_tags_without_accents():
    notes = [idea(1, title="Túnel"), idea(2, text="una VPN casera"), idea(3, tags=("hogar",)),
             idea(4)]
    found = lambda q: [n.title for n in choose_ideas(notes, IdeaView(q=q))]
    assert found("tunel") == ["Túnel"]
    assert found("vpn casera") == ["Idea 2"]
    assert found("#hogar") == ["Idea 3"]


def test_the_search_keeps_out_the_dropped_unless_asked():
    notes = [idea(1, "dropped", title="VPN")]
    assert choose_ideas(notes, IdeaView(q="vpn")) == []
    assert len(choose_ideas(notes, IdeaView(q="vpn", estado="dropped"))) == 1


def test_the_state_group_counts_each_state_and_all_without_the_dropped():
    notes = [idea(1), idea(2, "doing"), idea(3, "dropped"), idea(4, "typo")]
    group, = idea_filters(notes, IdeaView(estado="doing"))
    assert group["title"] == "STATE"
    rows = [(r["label"], r["count"], r["on"]) for r in group["rows"]]
    assert rows == [("All", 3, False), ("seed", 1, False), ("under way", 1, True),
                    ("done", 0, False), ("dropped", 1, False)]
    assert group["rows"][2]["href"] == "/ideas?estado=doing"
    assert group["rows"][2]["dot"] == "#a9b4de"


def test_a_filter_keeps_the_layout_and_drops_the_search():
    group, = idea_filters([idea(1)], IdeaView(q="x", vista="lista"))
    assert group["rows"][1]["href"] == "/ideas?estado=pending&vista=lista"
