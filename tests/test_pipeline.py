"""The pipeline: a URL in, a note out, and never a lost link."""

import datetime as dt
import json

import pytest

from oknowledge.config import Config
from oknowledge.extract import Unreadable
from oknowledge.model import Extracted
from oknowledge.pipeline import add, retry
from oknowledge.queue import Queue
from oknowledge.urls import link_id
from oknowledge.vault import all_notes, index_path, read_note

ANSWER = json.dumps({
    "title": "WireGuard vs OpenVPN",
    "summary": "Compara ambos protocolos.",
    "points": ["Corre en el kernel"],
    "category": "Redes",
    "tags": ["vpn"],
})

TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()

PAGE = Extracted(
    title="WireGuard vs OpenVPN | Ars",
    text="WireGuard runs inside the kernel...",
    type="article",
    source="arstechnica.com",
    author="Dan Goodin",
    published="2026-09-28",
    cover_url="https://cdn.example.com/wg.jpg",
)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",), engines={"fake": {"replies": [ANSWER]}})


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "state")


def extraction(monkeypatch, result):
    def fake(url):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("oknowledge.pipeline.extract", fake)


def no_cover(monkeypatch):
    monkeypatch.setattr("oknowledge.pipeline.download_cover", lambda cfg, url, link_id: None)


def test_a_good_link_becomes_a_finished_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    result = add(cfg, "https://arstechnica.com/vpn?utm_source=wa", queue=q)

    assert result.status == "ok"
    assert result.engine == "fake"
    note = read_note(result.path)
    assert note.title == "WireGuard vs OpenVPN"
    assert note.category == "Redes"
    assert note.tags == ["vpn"]
    assert note.author == "Dan Goodin"
    assert note.body == "WireGuard runs inside the kernel..."
    assert note.url == "https://arstechnica.com/vpn"
    assert q.get(note.id).status == "ok"


def test_the_category_index_is_written_too(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert "WireGuard" in index_path(cfg, "Redes").read_text(encoding="utf-8")


def test_summary_mode_drops_the_original_text(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    result = add(cfg, "https://arstechnica.com/vpn", content="summary", queue=q)
    assert read_note(result.path).body is None


def test_a_page_we_cannot_read_still_leaves_a_note(cfg, q, monkeypatch):
    # The rule that outranks the others: the link is never lost.
    extraction(monkeypatch, Unreadable("403 from the site"))

    result = add(cfg, "https://x.com/user/status/1", queue=q)

    assert result.status == "partial"
    note = read_note(result.path)
    assert note.url == "https://x.com/user/status/1"
    assert note.status == "partial"
    assert note.category == "Sin clasificar"
    assert note.saved
    assert q.get(note.id).status == "partial"
    assert "403" in q.get(note.id).error


def test_when_every_engine_fails_the_text_is_not_thrown_away(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg = Config(vault=cfg.vault, chain=("fake",), engines={"fake": {"replies": []}})

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "partial"
    note = read_note(result.path)
    assert note.title == "WireGuard vs OpenVPN | Ars"
    assert note.body == "WireGuard runs inside the kernel..."


def test_the_same_link_twice_does_not_duplicate(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    again = add(cfg, "https://www.arstechnica.com/vpn/?utm_source=x", queue=q)

    assert again.skipped is True
    assert len(all_notes(cfg)) == 1


def test_reprocess_rewrites_the_same_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    cfg.engines["fake"]["replies"] = [json.dumps({
        "title": "WireGuard vs OpenVPN", "summary": "Otro resumen.",
        "points": [], "category": "Redes", "tags": ["vpn"],
    })]
    second = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert second.path == first.path
    assert read_note(second.path).summary == "Otro resumen."
    assert len(all_notes(cfg)) == 1


def test_the_existing_categories_are_offered_to_the_model(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    seen = {}
    import oknowledge.pipeline as pipeline

    def spy(config, text, meta, known, engine=None):
        seen["known"] = list(known)
        from oknowledge.ai.base import Analysis
        return Analysis("T", "S", [], "Redes", ["vpn"]), "fake"

    monkeypatch.setattr(pipeline, "analyze_with_chain", spy)
    add(cfg, "https://arstechnica.com/a", queue=q)
    add(cfg, "https://arstechnica.com/b", queue=q)
    assert seen["known"] == ["Redes"]


def test_retry_finishes_what_was_left_half_done(cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("503"))
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert q.unfinished()

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["ok"]
    assert not q.unfinished()
    assert len(all_notes(cfg)) == 1


def test_a_page_too_long_for_the_model_says_so_in_the_note(cfg, q, monkeypatch):
    # The spec: if the text is longer than the model takes, the note says so.
    from oknowledge.ai.base import DEFAULT_LIMIT

    long_page = Extracted(title="Libro entero", text="x" * (DEFAULT_LIMIT + 1),
                          type="article", source="e.com")
    extraction(monkeypatch, long_page)
    no_cover(monkeypatch)

    result = add(cfg, "https://e.com/libro", queue=q)
    note = read_note(result.path)

    assert "más larga de lo que entra en el modelo" in note.summary
    assert note.body == "x" * (DEFAULT_LIMIT + 1)       # the original is kept whole


def test_the_cover_lands_in_attachments(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)

    class Fetched:
        content = b"\x89PNG fake bytes"
        content_type = "image/jpeg"

    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Fetched())

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)
    note = read_note(result.path)

    assert note.cover == f"../attachments/{note.id}.jpg"
    assert (cfg.attachments_dir / f"{note.id}.jpg").read_bytes() == b"\x89PNG fake bytes"


# --- The never-lose-a-link rule, one failure at a time ------------------------


def test_every_engine_failing_still_records_the_link(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = []

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    note = read_note(result.path)
    assert (note.url, note.status, note.category) == (
        "https://arstechnica.com/vpn", "partial", "Sin clasificar")
    entry = q.get(result.id)
    assert entry.status == "partial"
    assert "fake" in entry.error


def test_an_unreadable_page_in_an_english_vault_is_not_classified_in_spanish(
        cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("403 from the site"))
    english = Config(vault=cfg.vault, chain=("fake",), language="en",
                     engines={"fake": {"replies": []}})

    result = add(english, "https://x.com/user/status/1", queue=q)

    note = read_note(result.path)
    assert note.category == "Unclassified"
    assert note.source == "x.com"                  # from a real URL parse
    assert note.url == "https://x.com/user/status/1"
    assert "retry" in note.summary                 # the English partial summary


def test_an_extractor_bug_still_leaves_a_note_and_names_the_type(cfg, q, monkeypatch):
    # extract() promises to raise only Unreadable. The rule must not depend on
    # that promise: a bug in a library would otherwise cost the user the link.
    extraction(monkeypatch, RuntimeError("trafilatura exploded"))

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "partial"
    assert read_note(result.path).url == "https://arstechnica.com/vpn"
    error = q.get(result.id).error
    assert "RuntimeError" in error
    assert "trafilatura exploded" in error


def test_a_cover_we_cannot_download_does_not_cost_the_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)

    def explode(url, **kw):
        raise OSError("no space left on device")

    monkeypatch.setattr("oknowledge.pipeline.fetch", explode)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "ok"
    note = read_note(result.path)
    assert note.cover is None
    assert note.title == "WireGuard vs OpenVPN"


def test_an_error_page_is_not_saved_as_a_cover(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)

    class Fetched:
        content = b"<html>404 Not Found</html>"
        content_type = "text/html; charset=utf-8"

    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Fetched())

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert read_note(result.path).cover is None
    assert not list(cfg.attachments_dir.glob("*"))


def test_an_index_another_file_holds_is_reported_not_swallowed(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    mine = index_path(cfg, "Redes")
    mine.parent.mkdir(parents=True, exist_ok=True)
    mine.write_text("# My own notes on networks\n", encoding="utf-8")

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "ok"
    assert any("Redes.md" in warning for warning in result.warnings)
    assert mine.read_text(encoding="utf-8") == "# My own notes on networks\n"


def test_a_reindex_that_fails_does_not_lose_the_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    def explode(config, language):
        raise OSError("no space left on device")

    monkeypatch.setattr("oknowledge.pipeline.rebuild_indexes", explode)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "ok"
    assert read_note(result.path).title == "WireGuard vs OpenVPN"
    assert q.get(result.id).status == "ok"          # the status beats the reindex
    assert any("index" in warning for warning in result.warnings)


def test_the_status_is_recorded_before_the_reindex(cfg, q, monkeypatch):
    # _reindex() guards itself, so only a failure it cannot catch shows the
    # order. Ctrl-C during the rebuild is exactly that, and must still leave a
    # finished note with a finished entry instead of one stranded as pending.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    def interrupted(config, language):
        raise KeyboardInterrupt

    monkeypatch.setattr("oknowledge.pipeline.rebuild_indexes", interrupted)

    with pytest.raises(KeyboardInterrupt):
        add(cfg, "https://arstechnica.com/vpn", queue=q)

    note = all_notes(cfg)[0]
    assert note.title == "WireGuard vs OpenVPN"
    assert q.get(note.id).status == "ok"


def test_retry_picks_up_an_entry_whose_process_died(cfg, q, monkeypatch):
    url = "https://arstechnica.com/vpn"
    link = link_id(url)
    q.enqueue(link, url, "full")                    # enqueued, then the process died
    assert not q.unfinished()                       # pending: no retry would see it
    assert [e.id for e in q.orphaned()] == [link]

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["ok"]
    assert q.get(link).status == "ok"
    assert len(all_notes(cfg)) == 1


def test_a_locked_link_leaves_the_queue_alone(cfg, q, monkeypatch):
    url = "https://arstechnica.com/vpn"
    link = link_id(url)
    q.enqueue(link, url, "summary")
    q.set_status(link, "failed", error="the site was down", title="An old title")
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    with q.lock(link):
        result = add(cfg, url, queue=q)

    assert result.status == "pending"
    assert result.path is None
    entry = q.get(link)
    assert (entry.status, entry.error, entry.title, entry.content) == (
        "failed", "the site was down", "An old title", "summary")
    assert all_notes(cfg) == []


# --- The retried note's name, and one bad link among many ---------------------


def test_a_retried_note_is_renamed_after_its_new_title(cfg, q, monkeypatch):
    # A partial note is named after its URL, and that is the name Obsidian's
    # explorer and quick switcher show. Finishing it has to fix the name too.
    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert first.path.name == f"{TODAY}-https-arstechnica-com-vpn.md"

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    renamed = retry(cfg, queue=q)[0].path

    assert renamed.name == f"{TODAY}-wireguard-vs-openvpn.md"
    assert not first.path.exists()                  # moved, not copied
    notes = all_notes(cfg)
    assert [note.id for note in notes] == [first.id]
    # Renamed before the reindex, so the wikilink names the file that exists.
    assert f"[[{renamed.stem}|" in index_path(cfg, "Redes").read_text(encoding="utf-8")


def test_a_retried_note_keeps_its_name_when_the_new_one_is_taken(cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    squatter = cfg.links_dir / f"{TODAY}-wireguard-vs-openvpn.md"
    squatter.write_text("# My own file, no marker\n", encoding="utf-8")

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"
    assert result.path == first.path                # the name is left alone
    assert squatter.read_text(encoding="utf-8") == "# My own file, no marker\n"
    assert read_note(result.path).title == "WireGuard vs OpenVPN"
    assert len(all_notes(cfg)) == 1
    # Nothing failed, but the user is otherwise left with one oddly named note
    # and no way to find out why.
    assert any(squatter.name in warning for warning in result.warnings)


def test_one_link_that_cannot_be_written_does_not_stop_the_others(cfg, q, monkeypatch):
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    urls = [f"https://arstechnica.com/{name}" for name in ("a", "b", "c")]
    for url in urls:
        q.enqueue(link_id(url), url, "full")
    broken = link_id(urls[1])

    real = pipeline.write_note

    def picky(config, note, language, path=None):
        if note.id == broken:
            raise OSError("no space left on device")
        return real(config, note, language, path=path)

    monkeypatch.setattr(pipeline, "write_note", picky)

    results = retry(cfg, queue=q)

    assert len(results) == 3
    done = {result.id: result for result in results}
    assert [done[link_id(url)].status for url in urls] == ["ok", "failed", "ok"]
    failed = done[broken]
    assert failed.path is None
    assert "OSError" in failed.error
    assert "no space left on device" in failed.error
    assert q.get(broken).status == "failed"         # reported, and still retryable
    assert len(all_notes(cfg)) == 2                 # the other two landed


def test_a_rename_that_fails_keeps_the_note_and_says_so(cfg, q, monkeypatch):
    import types

    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    def refuse(src, dst):
        raise OSError("cross-device link")

    # Only the rename: patching os.replace itself would also break the atomic
    # write that put the note on disk in the first place.
    monkeypatch.setattr(pipeline, "os", types.SimpleNamespace(replace=refuse))

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"                    # only the name is wrong
    assert result.path == first.path
    assert read_note(first.path).title == "WireGuard vs OpenVPN"
    assert q.get(first.id).status == "ok"
    assert any("could not be renamed" in warning for warning in result.warnings)
    assert len(all_notes(cfg)) == 1


def test_reporting_a_failed_link_cannot_take_down_the_run(cfg, q, monkeypatch):
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    urls = ["https://arstechnica.com/a", "https://arstechnica.com/b"]
    for url in urls:
        q.enqueue(link_id(url), url, "full")
    broken = link_id(urls[0])

    real_write, real_status = pipeline.write_note, q.set_status

    def picky(config, note, language, path=None):
        if note.id == broken:
            raise OSError("no space left on device")
        return real_write(config, note, language, path=path)

    def full_disk(link, status, error=None, title=None):
        if status == "failed":
            raise OSError("no space left on device")
        return real_status(link, status, error=error, title=title)

    monkeypatch.setattr(pipeline, "write_note", picky)
    monkeypatch.setattr(q, "set_status", full_disk)

    results = retry(cfg, queue=q)

    done = {result.id: result for result in results}
    assert done[broken].status == "failed"
    assert done[link_id(urls[1])].status == "ok"    # the run carried on
    # The entry it could not even mark stays pending, which keeps it retryable.
    assert q.get(broken).status == "pending"
    assert [e.id for e in q.orphaned()] == [broken]


# --- A partial note never replaces an analyzed one ----------------------------


def test_a_failed_reanalysis_never_downgrades_a_finished_note(cfg, q, monkeypatch):
    # Overwriting an analyzed note with a partial one throws away the summary,
    # the points, the category and the tags: that is the user's content.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    good = read_note(first.path)

    cfg.engines["fake"]["replies"] = []                 # every engine is down now
    result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert result.status == "failed"                    # the Result reports it
    assert "fake" in result.error
    assert any("left as it is" in warning for warning in result.warnings)

    kept = read_note(first.path)
    assert (kept.summary, kept.points, kept.category, kept.tags) == (
        good.summary, good.points, good.category, good.tags)
    assert kept.status == "ok"
    assert result.path == first.path                    # not renamed either
    assert first.path.exists()
    assert len(all_notes(cfg)) == 1
    # Not reindexed, because nothing changed: the index still names the note.
    assert f"[[{first.path.stem}|" in index_path(cfg, "Redes").read_text(encoding="utf-8")
    # The link is saved and analyzed, so nothing is left to finish -- but the
    # reason the last attempt failed is still on disk.
    assert q.get(result.id).status == "ok"
    assert "fake" in q.get(result.id).error


def test_a_failed_extraction_never_downgrades_a_finished_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    good = read_note(first.path)

    extraction(monkeypatch, Unreadable("403 from the site"))
    result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert result.status == "failed"
    assert "403" in result.error
    assert read_note(first.path) == good                # byte for byte the same note
    assert result.path == first.path
    assert len(all_notes(cfg)) == 1
    assert q.get(result.id).status == "ok"


def test_a_reprocess_over_a_partial_note_still_rewrites_it(cfg, q, monkeypatch):
    # Partial over partial is idempotent and harmless: only an analyzed note is
    # protected.
    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert read_note(first.path).content == "full"

    extraction(monkeypatch, Unreadable("still 503"))
    again = add(cfg, "https://arstechnica.com/vpn", content="summary",
                reprocess=True, queue=q)

    assert again.status == "partial"
    assert not any("left as it is" in warning for warning in again.warnings)
    assert read_note(again.path).content == "summary"   # really rewritten
    assert q.get(again.id).error == "still 503"
    assert len(all_notes(cfg)) == 1


def test_a_protected_note_leaves_no_unfinished_work(cfg, q, monkeypatch):
    # A failed re-analysis of a link that is already saved and analyzed must not
    # leave a row the user can never clear.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    cfg.engines["fake"]["replies"] = []
    result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert result.status == "failed"                # this attempt did fail
    entry = q.get(first.id)
    assert entry.status == "ok"                     # nothing is left to finish
    assert "fake" in entry.error                    # the reason is still there
    assert q.unfinished() == []
    assert q.orphaned() == []                       # and not pending either


def test_retry_does_no_work_after_a_protected_failure(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    good = read_note(first.path)

    cfg.engines["fake"]["replies"] = []
    add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    def never(url):
        pytest.fail("retry re-attempted a link with nothing left to finish")

    monkeypatch.setattr("oknowledge.pipeline.extract", never)

    assert retry(cfg, queue=q) == []                # re-analysis stays the
    assert retry(cfg, queue=q) == []                # user's own act
    assert read_note(first.path) == good


def test_every_branch_reports_one_spelling_of_the_path(tmp_path, q, monkeypatch):
    # find_note() globs the configured path and write_note() resolves it, so a
    # vault reached through a symlink could give two paths for one note.
    real = tmp_path / "real"
    (real / "oknowledge" / "links").mkdir(parents=True)
    through = tmp_path / "vault"
    through.symlink_to(real, target_is_directory=True)
    cfg = Config(vault=through, chain=("fake",),
                 engines={"fake": {"replies": [ANSWER]}})
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    written = add(cfg, "https://arstechnica.com/vpn", queue=q)
    skipped = add(cfg, "https://arstechnica.com/vpn", queue=q)
    cfg.engines["fake"]["replies"] = []
    kept = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert skipped.skipped is True
    assert kept.status == "failed"
    assert written.path == skipped.path == kept.path
