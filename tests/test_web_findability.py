import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient

from oknowledge import i18n
from oknowledge.config import Config
from oknowledge.model import Mention, Note
from oknowledge.vault import write_note
from oknowledge.web.app import create_app
from oknowledge.urls import search_url
from oknowledge.web.index import fold, fold_map


def note(id, title, category="Misc", tags=(), summary="Resumen.", body=None,
         saved="2026-10-03", source="e.com", author=None, url=None, points=("p",),
         type="article", mentions=None, collections=()):
    return Note(id=id, url=url or f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type=type, source=source, saved=saved,
                summary=summary, points=list(points), author=author, body=body,
                mentions=mentions, collections=list(collections))


def make_cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def app_with(tmp_path, *notes):
    cfg = make_cfg(tmp_path)
    for n in notes:
        write_note(cfg, n, "es")
    return cfg, TestClient(create_app(cfg))


def hits(client, q):
    return client.get("/", params={"q": q}).text


def card(id):
    """How a note appears in the library column."""
    return f'id="card-{id}"'


# --- 1: folding keeps every script findable ------------------------------------------


@pytest.mark.parametrize("title,query", [
    ("日本語 の記事", "日本語"), ("привет мир", "привет"), ("Привет", "ПРИВЕТ"),
    ("Søren Kierkegaard", "Soren"), ("Łódź", "lodz"), ("Straße", "strasse"),
    ("Đà Nẵng", "da nang"), ("Æsop", "aesop"), ("cœur", "coeur"),
    ("Canción española", "CANCION ESPANOLA"), ("año", "ano"), ("한국어", "한국어"),
    ("が", "が"),
])
def test_search_finds_notes_by_their_own_words(tmp_path, title, query):
    _, client = app_with(tmp_path, note("n1", title))
    assert card("n1") in hits(client, query)


def test_japanese_voicing_marks_are_part_of_the_letter(tmp_path):
    assert fold("が") != fold("か")
    _, client = app_with(tmp_path, note("n1", "が"))
    assert card("n1") not in hits(client, "か")


def test_folding_does_not_conflate_other_scripts():
    assert fold("日本語") != fold("中文")
    assert fold("привет") == "привет"


@pytest.mark.parametrize("text", ["Plain ASCII\ttext\nhere", "Canción de Peña", "日本語 が",
                                  "Straße æ", "mixed ASCII y ñ\r\nline", ""])
def test_the_fast_path_and_the_full_fold_agree(text):
    assert fold(text) == fold_map(text)[0]


def test_fold_map_points_every_folded_char_home():
    text = "¿Qué “año”?"
    folded, offsets = fold_map(text)
    assert len(folded) == len(offsets)
    for char, home in zip(folded, offsets):
        assert text[home].casefold()[:1] == char or char == " " or char.isascii()


# --- 2: the body and the summary are searched ------------------------------------------


def test_the_body_is_searched_after_spanish_punctuation(tmp_path):
    body = "¿Qué? ¡Sí! — “hola” " * 40 + "la palabra buscada aparece aquí " + "x " * 100
    _, client = app_with(tmp_path, note("n1", "Titulo", body=body))
    assert card("n1") in hits(client, "buscada")


def test_the_body_is_searched_after_cjk(tmp_path):
    body = "日本語の文章です。" * 40 + " needle here"
    _, client = app_with(tmp_path, note("n1", "T", body=body))
    assert card("n1") in hits(client, "needle")


def test_the_body_is_searched_after_letters_that_fold_to_two(tmp_path):
    body = "Straße æsop cœur " * 30 + "la aguja buscada " + "y " * 100
    _, client = app_with(tmp_path, note("n1", "T", body=body))
    assert card("n1") in hits(client, "aguja")


def test_an_accented_summary_is_found_without_its_accents(tmp_path):
    _, client = app_with(tmp_path, note("n1", "T", summary="Sobre la canción de Peña."))
    assert card("n1") in hits(client, "cancion")


# --- 3: terms, not one literal phrase -------------------------------------------------


def test_every_term_must_match_across_fields(tmp_path):
    _, client = app_with(
        tmp_path,
        note("n1", "WireGuard", tags=["vpn"], summary="Algo sobre redes."),
        note("n2", "WireGuard solo", summary="Nada."),
    )
    text = hits(client, "wireguard redes")
    assert card("n1") in text and card("n2") not in text


def test_a_hash_prefix_matches_the_tag_as_displayed(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno", tags=["vpn"]), note("n2", "Dos"))
    text = hits(client, "#vpn")
    assert card("n1") in text and card("n2") not in text


def test_a_phrase_split_by_a_line_break_still_matches(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno", body="the quick\nbrown fox"))
    assert card("n1") in hits(client, "quick brown")


def test_a_term_that_is_nowhere_means_no_hit(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno"))
    text = hits(client, "uno zzzz")
    assert card("n1") not in text and "Nothing matches" in text


# --- 4: source, author and url are searchable -----------------------------------------


@pytest.mark.parametrize("query", ["nytimes", "Jane Doe", "zebra-article"])
def test_source_author_and_url_are_searchable(tmp_path, query):
    _, client = app_with(tmp_path, note(
        "n1", "Un titulo", source="nytimes.com", author="Jane Doe",
        url="https://example.org/zebra-article"))
    assert card("n1") in hits(client, query)


# --- 5: a vanished vault is an error --------------------------------------------------


def test_a_moved_vault_is_an_error_not_an_empty_library(tmp_path):
    cfg, client = app_with(tmp_path, note("n1", "Uno"))
    assert "Uno" in client.get("/").text
    moved = tmp_path / "elsewhere"
    cfg.vault.rename(moved)
    response = client.get("/")
    assert response.status_code == 503
    assert "The vault could not be read" in response.text
    assert str(cfg.root) in response.text
    assert "Nothing saved yet" not in response.text
    moved.rename(cfg.vault)
    assert client.get("/").status_code == 200


def test_a_vanished_vault_leaves_nothing_behind_to_offer(tmp_path):
    """Not only the cards: the chips are read out of what was there, and a
    library that cannot be read has no categories, tags or collections to
    offer -- least of all as a list to file something into."""
    cfg, client = app_with(tmp_path, note("n1", "Uno", category="Redes", tags=["vpn"],
                                          collections=["Casa"], saved="2021-11-05"))
    library = client.app.state.library
    assert library.collections() == {"Casa": 1} and library.years() == {"2021": 1}

    cfg.vault.rename(tmp_path / "elsewhere")
    library.refresh()

    assert (library.categories(), library.tags(), library.collections(),
            library.years(), library.months()) == ({}, {}, {}, {}, {})


def test_a_missing_vault_at_startup_is_an_error(tmp_path):
    client = TestClient(create_app(Config(vault=tmp_path / "nope")))
    assert client.get("/").status_code == 503


def test_a_missing_links_folder_under_an_existing_root_is_just_empty(tmp_path):
    cfg = make_cfg(tmp_path)
    shutil.rmtree(cfg.links_dir)
    response = TestClient(create_app(cfg)).get("/")
    assert response.status_code == 200
    assert "Nothing saved yet" in response.text


# --- 6: scale: bodies are not retained, only changed files are re-parsed ---------------


def test_the_index_does_not_retain_bodies(tmp_path):
    cfg, client = app_with(tmp_path, note("n1", "Uno", body="SECRETBODY " * 50))
    library = client.app.state.library
    assert all(entry.note.body is None for entry in library.entries)
    assert "SECRETBODY" in client.get("/item/n1").text  # the item page reads it fresh


def test_the_item_page_shows_edits_made_since_the_last_refresh(tmp_path):
    cfg, client = app_with(tmp_path, note("n1", "Uno", body="old body"))
    path = next(cfg.links_dir.glob("*.md"))
    path.write_text(path.read_text(encoding="utf-8").replace("old body", "new body"),
                    encoding="utf-8")
    assert "new body" in client.get("/item/n1").text


def test_touching_one_file_reparses_only_that_file(tmp_path, monkeypatch):
    from oknowledge.web import index

    cfg, client = app_with(tmp_path, *[note(f"n{i}", f"Titulo {i}") for i in range(5)])
    parsed = []
    real = index.scan_file
    monkeypatch.setattr(index, "scan_file", lambda p: (parsed.append(p.name), real(p))[1])
    target = sorted(cfg.links_dir.glob("*.md"))[2]
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    client.get("/")
    assert parsed == [target.name]


def test_a_bad_length_is_the_first_chunk(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno"))
    for bad in ("abc", "0", "-3", "99999"):
        answer = client.get("/", params={"hasta": bad})
        assert answer.status_code == 200 and card("n1") in answer.text


def test_hits_are_ranked_title_then_summary_then_source_then_body(tmp_path):
    _, client = app_with(
        tmp_path,
        note("body", "Zzz", body="mention of gizmo"),
        note("src", "Yyy", source="gizmo.com"),
        note("sum", "Xxx", summary="a gizmo review"),
        note("tit", "Gizmo", saved="2020-01-01"),
    )
    text = hits(client, "gizmo")
    order = [text.index(card(i)) for i in ("tit", "sum", "src", "body")]
    assert order == sorted(order)


def test_equal_rank_breaks_ties_by_date_then_file_time(tmp_path):
    cfg = make_cfg(tmp_path)
    for n, day in (("old", "2026-01-01"), ("new", "2026-02-01")):
        write_note(cfg, note(n, f"gizmo {n}", saved=day), "es")
    text = TestClient(create_app(cfg)).get("/?q=gizmo").text
    assert text.index(card("new")) < text.index(card("old"))


def test_same_day_notes_show_the_most_recently_saved_first(tmp_path):
    cfg = make_cfg(tmp_path)
    paths = [write_note(cfg, note(f"n{i}", f"{t}"), "es")
             for i, t in enumerate(["Zeta", "Alfa", "Mike"])]
    for i, path in enumerate(paths):       # Zeta oldest ... Mike newest
        os.utime(path, ns=(10**18, 10**18 + i * 10**10))
    body = TestClient(create_app(cfg)).get("/").text
    assert body.index("Mike") < body.index("Alfa") < body.index("Zeta")


def test_refreshes_never_overlap(tmp_path):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    _, client = app_with(tmp_path, note("n1", "Uno"))
    library = client.app.state.library
    running, worst, guard = [0], [0], threading.Lock()
    real = library._refresh

    def watched():
        with guard:
            running[0] += 1
            worst[0] = max(worst[0], running[0])
        time.sleep(0.01)
        real()
        with guard:
            running[0] -= 1

    library._refresh = watched
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: library.refresh(), range(16)))
    assert worst[0] == 1


def test_concurrent_refreshes_agree(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    cfg, client = app_with(tmp_path, *[note(f"n{i}", f"T{i}") for i in range(20)])
    library = client.app.state.library
    path = sorted(cfg.links_dir.glob("*.md"))[0]
    os.utime(path, ns=(10**18, 10**18 + 7))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: library.refresh(), range(40)))
    assert len(library.entries) == 20 and library.unreadable == 0


# --- 7: display and robustness ---------------------------------------------------------


def test_long_titles_may_wrap_anywhere():
    from pathlib import Path

    import oknowledge.web

    css = (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text()
    assert css.count("overflow-wrap: anywhere") >= 1
    block = css.split("overflow-wrap: anywhere")[0].rsplit("}", 1)[-1]
    for selector in (".card h2", ".hits", ".item h1", ".meta"):
        assert selector in block


def test_an_unknown_item_is_an_html_404(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno"))
    response = client.get("/item/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert '<aside class="sidebar"' in response.text


def test_a_blank_query_shows_the_library_not_no_results(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno"))
    for q in ("", "   ", "#"):
        response = client.get("/", params={"q": q})
        assert "Nothing matches" not in response.text and card("n1") in response.text


def test_an_empty_category_says_so(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Uno", category="Redes"))
    text = client.get("/?category=Gone").text
    assert "There is nothing in Gone" in text
    assert "Nothing saved yet" not in text


def test_pages_have_their_own_titles(tmp_path):
    _, client = app_with(tmp_path, note("n1", "Mi <titulo>"))
    assert "<title>oknowledge</title>" in client.get("/").text
    assert "<title>Mi &lt;titulo&gt; - oknowledge</title>" in client.get("/item/n1").text
    assert "<title>zz - oknowledge</title>" in client.get("/search?q=zz").text


def cover_for(tmp_path, filename, data=b"DATA"):
    cfg = make_cfg(tmp_path)
    cfg.attachments_dir.mkdir(parents=True)
    n = note("n1", "Uno")
    n.cover = f"../attachments/{filename}"
    write_note(cfg, n, "es")
    (cfg.attachments_dir / filename).write_bytes(data)
    return TestClient(create_app(cfg))


def test_the_cover_route_serves_images_with_nosniff(tmp_path):
    response = cover_for(tmp_path, "n1.png").get("/cover/n1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name", ["n1.svg", "n1.html", "n1.txt", "n1"])
def test_the_cover_route_refuses_anything_that_is_not_a_known_image(tmp_path, name):
    assert cover_for(tmp_path, name).get("/cover/n1").status_code == 404


def inside(markup: str, opening: str, closing: str) -> str:
    """What one element holds, so a test can ask whether `dir` governs it.

    What carries dir="auto" decides the direction of everything inside it,
    descendants included.
    """
    start = markup.index(opening) + len(opening)
    return markup[start:markup.index(closing, start)]


def test_titles_and_summaries_are_direction_neutral(tmp_path):
    _, client = app_with(tmp_path, note("n1", "שלום", summary="مرحبا"))
    home = client.get("/").text
    assert "שלום" in inside(home, '<span class="title" dir="auto">', "</span>")
    item = client.get("/item/n1").text
    assert '<h1 dir="auto">שלום' in item and '<div class="summary" dir="auto">' in item
    found = hits(client, "שלום")
    assert '<span class="title" dir="auto">שלום' in found


def test_ids_are_url_encoded_in_links(tmp_path):
    cfg, client = app_with(tmp_path, note("a b?c#d", "Uno"))
    path = next(cfg.links_dir.glob("*.md"))
    path.write_text(path.read_text(encoding="utf-8").replace(
        "status:", "cover: ../attachments/x.png\nstatus:", 1), encoding="utf-8")
    text = client.get("/").text
    assert "sel=a+b%3Fc%23d" in text and "/cover/a%20b%3Fc%23d" in text
    assert "sel=a b" not in text


# --- 8: what a video mentioned is searchable ------------------------------------------
#
# The point of the mentions is to go on investigating: the name has to be a way
# back to the video. The transcript is only in the body when the note was saved
# with content == full, it ranks last when it is, and the name the model wrote
# is not always the one the speaker said.


def video(id, title, mentions, **rest):
    return note(id, title, type="youtube", source="youtu.be",
                url=f"https://youtu.be/{id}", mentions=mentions, **rest)


def test_a_mention_name_is_searchable(tmp_path):
    _, client = app_with(tmp_path, video(
        "v1", "Un video", [Mention(name="OpenCode", url="https://opencode.ai")]))

    assert card("v1") in hits(client, "opencode")


def test_a_mention_is_found_though_the_transcript_said_the_name_differently(tmp_path):
    """The model writes the name as a name; the speaker said two words. Without
    the mentions tier the only copy is the transcript's, which does not match."""
    _, client = app_with(tmp_path, video(
        "v1", "Un video", [Mention(name="OpenCode", url="https://opencode.ai")],
        body="y despues probamos open code un rato"))

    assert card("v1") in hits(client, "opencode")


def test_a_domain_the_video_really_named_is_searchable(tmp_path):
    _, client = app_with(tmp_path, video(
        "v1", "Un video", [Mention(name="OpenCode", url="https://opencode.ai")]))

    assert card("v1") in hits(client, "opencode.ai")


def test_a_search_link_does_not_make_its_search_engine_searchable(tmp_path):
    """A name with no URL gets a search link, and every one of them shares a
    host. Folding those in would make one query return every video that ever
    named something without a link."""
    _, client = app_with(tmp_path, video(
        "v1", "Un video", [Mention(name="Gizmo", url=search_url("Gizmo"))]))

    assert card("v1") in hits(client, "gizmo")
    assert card("v1") not in hits(client, "duckduckgo")


def test_a_note_about_the_term_outranks_a_video_that_only_mentioned_it(tmp_path):
    _, client = app_with(
        tmp_path,
        video("v1", "Un video", [Mention(name="Gizmo", url="https://gizmo.dev")],
              saved="2026-01-01"),
        note("n1", "Otra cosa", summary="a gizmo review", saved="2020-01-01"),
    )
    text = hits(client, "gizmo")

    assert text.index(card("n1")) < text.index(card("v1"))


def test_a_mention_outranks_the_same_word_buried_in_a_transcript(tmp_path):
    _, client = app_with(
        tmp_path,
        note("n1", "Otra cosa", body="al pasar dijo gizmo y siguio", saved="2026-01-01"),
        video("v1", "Un video", [Mention(name="Gizmo", url="https://gizmo.dev")],
              saved="2020-01-01"),
    )
    text = hits(client, "gizmo")

    assert text.index(card("v1")) < text.index(card("n1"))


