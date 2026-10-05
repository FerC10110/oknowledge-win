"""The pipeline: a URL in, a note out, and never a lost link."""

import datetime as dt
import json
import os

import pytest

from oknowledge.config import Config
from oknowledge.extract import Unreadable
from oknowledge.model import Extracted
from oknowledge.pipeline import add, retry
from oknowledge.queue import Locked, Queue, state_dir
from oknowledge.urls import link_id, normalize
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


@pytest.fixture(autouse=True)
def state_under_tmp_path(tmp_path, monkeypatch):
    """Every add() here passes queue=q, so nothing reaches the default state
    tree -- but that is a convention, not a guarantee. Pin it, the way
    test_cli.py and test_web_write.py do, so one forgotten `queue=` writes
    into tmp_path instead of the user's ~/.local/state."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


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
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    class OnlyTheRenameFails:
        """The real os with one call swapped out. A SimpleNamespace would make
        the next os.* call anywhere in _save fail with an AttributeError
        naming neither cause nor fix, and patching os.replace itself would
        break the atomic write that puts the note on disk."""

        def __getattr__(self, name):
            return getattr(os, name)

        @staticmethod
        def replace(src, dst):
            raise OSError("cross-device link")

    monkeypatch.setattr(pipeline, "os", OnlyTheRenameFails())

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


# --- The queue is bookkeeping; the note is the artifact -----------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 0o500 does not bite as root")
def test_an_unwritable_state_tree_still_leaves_a_note(cfg, tmp_path, monkeypatch):
    # The state tree lives under $XDG_STATE_HOME and the vault is usually on
    # another filesystem: a full /home, a locks/ left root-owned by one sudo
    # run or an unmounted state tree must not cost the user a writable vault.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    state = tmp_path / "readonly-state"
    state.mkdir()
    state.chmod(0o500)
    try:
        result = add(cfg, "https://arstechnica.com/vpn", queue=Queue(state))
    finally:
        state.chmod(0o700)

    assert result.status == "ok"
    note = read_note(result.path)
    assert note.url == "https://arstechnica.com/vpn"
    assert note.title == "WireGuard vs OpenVPN"
    assert any("queue" in warning for warning in result.warnings)


def test_a_queue_entry_that_cannot_be_written_still_leaves_a_note(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    def full_disk(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(q, "enqueue", full_disk)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "ok"
    assert read_note(result.path).url == "https://arstechnica.com/vpn"
    assert any("no space left on device" in warning for warning in result.warnings)
    assert any("retry" in warning for warning in result.warnings)


def test_the_duplicate_scan_happens_inside_the_lock(cfg, q, monkeypatch):
    # From outside the lock the scan can miss a note another process is halfway
    # through writing, and we would write a second file for the same link.
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    real = pipeline.find_note
    seen = {}

    def spy(config, link):
        with pytest.raises(Locked):             # the lock is ours already
            with q.lock(link):
                pass
        seen["locked"] = True
        return real(config, link)

    monkeypatch.setattr(pipeline, "find_note", spy)

    assert add(cfg, "https://arstechnica.com/vpn", queue=q).status == "ok"
    assert seen["locked"]


# --- The vault's containment, and the user's own edits ------------------------


def test_the_rename_never_leaves_the_vault(cfg, q, tmp_path, monkeypatch):
    # The ideal path is resolved before anything moves onto it, so a dangling
    # symlink at that name resolves to its target and the note is written
    # there, outside the vault. (rename(2) does not follow a destination
    # symlink: it would replace the link itself, destroying a file of the
    # user's instead. Resolving is what avoids that and what causes this.)
    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    outside = tmp_path / "outside" / "stolen.md"
    outside.parent.mkdir()
    trap = cfg.links_dir / f"{TODAY}-wireguard-vs-openvpn.md"
    trap.symlink_to(outside)
    assert not trap.exists() and trap.is_symlink()

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"
    assert result.path == first.path                    # the name is kept
    assert not outside.exists()                         # nothing escaped
    assert read_note(first.path).title == "WireGuard vs OpenVPN"
    assert any(trap.name in warning for warning in result.warnings)


def test_a_squatter_too_broken_to_read_is_still_a_squatter(cfg, q, monkeypatch):
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    taken = cfg.links_dir / f"{TODAY}-wireguard-vs-openvpn.md"
    taken.write_text("---\noknowledge: 1\n---\n# deep\n", encoding="utf-8")
    real = pipeline.read_note

    def explode(path):
        if path.name == taken.name:
            raise RecursionError("maximum recursion depth exceeded")
        return real(path)

    monkeypatch.setattr(pipeline, "read_note", explode)
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"                        # a Result, not a traceback
    assert result.path == first.path
    assert any(taken.name in warning for warning in result.warnings)


def test_a_note_the_user_marked_their_own_way_is_protected_too(cfg, q, monkeypatch):
    # This vault is edited by hand: that is its whole premise.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    first.path.write_text(
        first.path.read_text(encoding="utf-8").replace("status: ok", "status: done"),
        encoding="utf-8")
    good = read_note(first.path)
    assert good.status == "done"

    cfg.engines["fake"]["replies"] = []
    result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert result.status == "failed"
    assert read_note(first.path) == good                # content and name intact
    assert result.path == first.path
    assert len(all_notes(cfg)) == 1


def test_a_note_too_broken_to_index_is_reported(cfg, q, monkeypatch):
    # The same hand-broken note that makes find_note() blind also drops out of
    # every index. We cannot identify it; we can at least say it is there.
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    broken = cfg.links_dir / "2026-01-01-hand-broken.md"
    broken.write_text("---\noknowledge: 1\ntitle: [unclosed\n---\n# x\n",
                      encoding="utf-8")

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert result.status == "ok"
    assert any(broken.name in warning for warning in result.warnings)
    assert broken.read_text(encoding="utf-8").startswith("---")     # never touched


# --- The content mode ---------------------------------------------------------


def test_the_truncation_notice_does_not_promise_a_body_it_did_not_keep(
        cfg, q, monkeypatch):
    from oknowledge.ai.base import DEFAULT_LIMIT

    long_page = Extracted(title="Libro entero", text="x" * (DEFAULT_LIMIT + 1),
                          type="article", source="e.com")
    extraction(monkeypatch, long_page)
    no_cover(monkeypatch)

    note = read_note(add(cfg, "https://e.com/libro", content="summary", queue=q).path)

    assert note.body is None
    assert "más larga de lo que entra en el modelo" in note.summary
    assert "más abajo" not in note.summary               # there is nothing below


def test_a_hand_edited_content_mode_is_not_taken_at_face_value(cfg, q, monkeypatch):
    # The queue's JSON is read by the QML widget, so it gets hand-edited, and
    # anything other than "full" silently means "keep no body".
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    url = "https://arstechnica.com/vpn"
    q.enqueue(link_id(url), url, "fulll")

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"
    note = read_note(result.path)
    assert (note.content, note.body) == ("full", PAGE.text)
    assert any("content mode" in warning for warning in result.warnings)


def test_a_plain_reprocess_keeps_a_saved_body(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg = Config(vault=cfg.vault, chain=("fake",), default_content="summary",
                 engines={"fake": {"replies": [ANSWER]}})
    first = add(cfg, "https://arstechnica.com/vpn", content="full", queue=q)
    assert read_note(first.path).body == PAGE.text

    second = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    note = read_note(second.path)
    assert (note.content, note.body) == ("full", PAGE.text)      # inherited


def test_a_symlink_at_the_ideal_name_is_treated_as_taken(cfg, q, monkeypatch):
    # A symlink resolving inside the folder passes containment, and a dangling
    # one is invisible to exists(). The ideal path is resolved before the move,
    # so without this guard the note lands under the name the symlink chose and
    # the user's symlink ends up pointing at our note.
    extraction(monkeypatch, Unreadable("503"))
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    ghost = cfg.links_dir / "ghost.md"
    trap = cfg.links_dir / f"{TODAY}-wireguard-vs-openvpn.md"
    trap.symlink_to(ghost)
    assert not trap.exists() and trap.is_symlink()

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]

    result = retry(cfg, queue=q)[0]

    assert result.status == "ok"
    assert result.path == first.path                    # the name is kept
    assert not ghost.exists()                           # nothing landed there
    assert trap.is_symlink()                            # the user's link intact
    assert any(trap.name in warning for warning in result.warnings)


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 0o500 does not bite as root")
def test_a_status_that_cannot_be_recorded_still_names_and_indexes_the_note(
        cfg, tmp_path, monkeypatch):
    # With an entry already on disk, set_status() reaches atomic_write and a
    # read-only queue tree raises from there -- after the note is written, and
    # before the rename and the reindex. This is the interactive path: retry()
    # absorbs it through _failed, a direct add() does not.
    extraction(monkeypatch, Unreadable("503"))
    q = Queue(tmp_path / "state")
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert q.get(first.id).status == "partial"

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]
    q.dir.chmod(0o500)
    try:
        result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)
    finally:
        q.dir.chmod(0o700)

    assert result.status == "ok"
    assert any("status" in warning for warning in result.warnings)
    # The note is correctly named and listed, which is the point of carrying on.
    assert result.path.name == f"{TODAY}-wireguard-vs-openvpn.md"
    assert read_note(result.path).title == "WireGuard vs OpenVPN"
    assert f"[[{result.path.stem}|" in index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert q.get(first.id).status == "partial"          # the write really failed


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 0o500 does not bite as root")
def test_a_protected_note_survives_a_queue_it_cannot_write(cfg, tmp_path, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    q = Queue(tmp_path / "state")
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    good = read_note(first.path)

    cfg.engines["fake"]["replies"] = []
    q.dir.chmod(0o500)
    try:
        result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)
    finally:
        q.dir.chmod(0o700)

    assert result.status == "failed"                    # a Result, not a traceback
    assert read_note(first.path) == good
    assert any("status" in warning for warning in result.warnings)
    assert any("left as it is" in warning for warning in result.warnings)


def test_the_rename_can_never_write_outside_the_links_folder(cfg, q, monkeypatch):
    # note_stem() sanitizes to [A-Za-z0-9-], which is what makes the containment
    # check unreachable today. The check is there so that a future change to
    # that character class cannot silently become a write outside the vault, so
    # the invariant is pinned rather than assumed.
    import oknowledge.pipeline as pipeline

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)

    for stem in ("../escape", "../../../../escape"):
        escapee = (cfg.links_dir / f"{stem}.md").resolve()
        monkeypatch.setattr(pipeline, "note_stem", lambda note, s=stem: s)

        result = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

        assert result.status == "ok"
        assert result.path == first.path                # the name is kept
        assert not escapee.exists()                     # nothing was written there
        assert any("escape.md" in warning for warning in result.warnings)
    assert len(all_notes(cfg)) == 1


def test_the_state_directory_is_under_tmp_path(tmp_path):
    assert state_dir().is_relative_to(tmp_path)


# --- retry reconciles; it never re-analyses a finished note -------------------
#
# The guard in _process() is read only by _give_up(), so every existing test of
# it exercises a FAILED analysis. The hole is the success path: extraction and
# analysis both work, _save() writes the fresh note over the file, and days of
# the user's own editing go with it. retry() is where that is reachable without
# anyone asking for it.


def hand_edit(path, status="done"):
    """What the user's own editing looks like: our marker, their status, their
    prose. Returns the exact bytes that must survive a retry."""
    text = path.read_text(encoding="utf-8")
    if status:
        text = text.replace("status: ok", f"status: {status}")
    else:
        text = "\n".join(l for l in text.splitlines() if not l.startswith("status:")) + "\n"
    text = text.replace("title: WireGuard vs OpenVPN", "title: Mi resumen de WireGuard")
    text += "\n## Lo que pienso\n\nEsto lo escribí yo y no lo quiero perder.\n"
    path.write_text(text, encoding="utf-8")
    return text


def died_after_saving(q, link, url, mode="full"):
    """Re-create the entry a process that died between writing the note and
    recording its status leaves behind: pending, and nobody holding the lock."""
    q.enqueue(link, url, mode)
    assert [e.id for e in q.orphaned()] == [link]
    assert not q.unfinished()


def test_retry_over_an_orphaned_entry_keeps_a_finished_note_byte_for_byte(
        cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    died_after_saving(q, saved.id, "https://arstechnica.com/vpn")
    mine = hand_edit(saved.path)

    # Both would succeed. This is the gap: the old guard was never consulted
    # on the path that writes.
    extraction(monkeypatch, PAGE)
    cfg.engines["fake"]["replies"] = [ANSWER]
    results = retry(cfg, queue=q)

    assert saved.path.read_text(encoding="utf-8") == mine
    assert q.get(saved.id).status == "ok"
    assert not q.orphaned() and not q.unfinished()
    assert [r.status for r in results] == ["ok"]
    assert results[0].skipped is True
    assert results[0].path == saved.path


def test_retry_over_a_failed_entry_keeps_a_finished_note_byte_for_byte(
        cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    q.set_status(saved.id, "failed", error="the site was down")
    mine = hand_edit(saved.path)

    cfg.engines["fake"]["replies"] = [ANSWER]
    retry(cfg, queue=q)

    assert saved.path.read_text(encoding="utf-8") == mine
    assert q.get(saved.id).status == "ok"


def test_reconciling_asks_no_engine_and_fetches_no_page(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    died_after_saving(q, saved.id, "https://arstechnica.com/vpn")

    def never(url):
        pytest.fail("retry fetched a page for a link whose note is finished")

    monkeypatch.setattr("oknowledge.pipeline.extract", never)
    cfg.engines["fake"]["replies"] = []          # an engine call would raise too

    assert [r.status for r in retry(cfg, queue=q)] == ["ok"]


@pytest.mark.parametrize("status", ["ok", "done", "reviewed", ""])
def test_any_status_but_partial_is_the_users_content(cfg, q, monkeypatch, status):
    """`partial` is the one value we write to mean unfinished. A deleted status
    line reads back as ok, so it has to fall on the protected side too."""
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    died_after_saving(q, saved.id, "https://arstechnica.com/vpn")
    mine = hand_edit(saved.path, status=status)

    cfg.engines["fake"]["replies"] = [ANSWER]
    retry(cfg, queue=q)

    assert saved.path.read_text(encoding="utf-8") == mine


def test_retry_still_finishes_a_partial_note(cfg, q, monkeypatch):
    """The other half of the rule: an unfinished note of ours is exactly what
    retry exists for, and it is replaced."""
    extraction(monkeypatch, Unreadable("503"))
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert read_note(saved.path).status == "partial"

    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]
    results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["ok"]
    assert results[0].skipped is False
    assert read_note(results[0].path).title == "WireGuard vs OpenVPN"
    assert read_note(results[0].path).status == "ok"


def test_retry_still_saves_a_link_whose_note_never_landed(cfg, q, monkeypatch):
    """The prime rule. An entry with no note at all is real work owed."""
    url = "https://arstechnica.com/vpn"
    q.enqueue(link_id(url), url, "full")
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)

    results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["ok"]
    assert len(all_notes(cfg)) == 1
    assert q.get(link_id(url)).status == "ok"


def test_an_explicit_reprocess_still_replaces_a_finished_note(cfg, q, monkeypatch):
    """Asking for a fresh analysis is the one thing that replaces note content,
    and the web's button has carried a confirmation since task 13."""
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    hand_edit(saved.path)
    assert read_note(saved.path).title == "Mi resumen de WireGuard"

    cfg.engines["fake"]["replies"] = [ANSWER]
    again = add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert again.status == "ok" and again.skipped is False
    assert read_note(again.path).title == "WireGuard vs OpenVPN"


def test_a_note_saved_at_summary_stays_there_until_asked_again(cfg, q, monkeypatch):
    """The accepted trade-off: the entry asks for `full`, the finished note is
    `summary`, and a hand edit is worth more than an automatic upgrade."""
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", content="summary", queue=q)
    assert read_note(saved.path).body is None
    died_after_saving(q, saved.id, "https://arstechnica.com/vpn", mode="full")

    cfg.engines["fake"]["replies"] = [ANSWER]
    retry(cfg, queue=q)

    assert read_note(saved.path).body is None
    assert q.get(saved.id).status == "ok"

    # ... and asking explicitly is what upgrades it.
    cfg.engines["fake"]["replies"] = [ANSWER]
    add(cfg, "https://arstechnica.com/vpn", content="full", reprocess=True, queue=q)
    assert read_note(saved.path).body is not None


def test_reconciling_says_what_it_did(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    died_after_saving(q, saved.id, "https://arstechnica.com/vpn")

    result = retry(cfg, queue=q)[0]

    assert "re-analys" in " ".join(result.warnings)
    assert result.error is None


def test_a_link_somebody_else_holds_is_left_for_them(cfg, q, monkeypatch):
    """A `failed` entry is offered to retry whoever holds the lock (only
    `pending` is gated on that), so this is the path that has to refuse."""
    extraction(monkeypatch, PAGE)
    no_cover(monkeypatch)
    saved = add(cfg, "https://arstechnica.com/vpn", queue=q)
    q.set_status(saved.id, "failed", error="the site was down")
    mine = hand_edit(saved.path)

    with q.lock(saved.id):
        results = retry(cfg, queue=q)

    assert [r.status for r in results] == ["pending"]
    assert saved.path.read_text(encoding="utf-8") == mine
    assert q.get(saved.id).status == "failed"      # not settled by somebody else


# --- the cover is a write into the vault, so it is contained like one (F1) ---
# download_cover was the one write that did not pass ensure_inside_root, and
# write_bytes follows symlinks: an attachments/ symlinked out of the vault put
# the file outside the managed folder, and a symlink named <link_id>.jpg let a
# downloaded image replace whatever it pointed at.

class Jpeg:
    content = b"\x89PNG not really"
    content_type = "image/jpeg"


def cover_fetches(monkeypatch):
    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Jpeg())


def test_a_cover_is_not_written_through_a_symlinked_attachments_folder(
        cfg, q, monkeypatch, tmp_path):
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    cfg.attachments_dir.parent.mkdir(parents=True, exist_ok=True)
    cfg.attachments_dir.symlink_to(outside, target_is_directory=True)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert list(outside.iterdir()) == [], "the cover was written outside the vault"
    assert read_note(result.path).cover is None
    assert result.status == "ok"             # a refused cover never costs the note


def test_a_cover_does_not_replace_the_file_a_symlink_points_at(
        cfg, q, monkeypatch, tmp_path):
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)
    photos = tmp_path / "photos"
    photos.mkdir()
    family = photos / "family.jpg"
    family.write_bytes(b"the picture of my family")
    link = link_id(normalize("https://arstechnica.com/vpn"))
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
    (cfg.attachments_dir / f"{link}.jpg").symlink_to(family)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert family.read_bytes() == b"the picture of my family"
    assert read_note(result.path).cover is None
    assert result.status == "ok"


def test_a_cover_still_lands_when_nothing_is_symlinked(cfg, q, monkeypatch):
    """The guard must not cost the normal case."""
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)
    note = read_note(result.path)

    assert note.cover == f"../attachments/{note.id}.jpg"
    assert (cfg.attachments_dir / f"{note.id}.jpg").read_bytes() == Jpeg.content


def test_a_cover_leaves_no_temporary_file_behind(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)
    add(cfg, "https://arstechnica.com/vpn", queue=q)
    assert [p.name for p in cfg.attachments_dir.iterdir() if p.name.startswith(".")] == []


def test_a_cover_replaces_the_old_file_instead_of_writing_into_it(cfg, q, monkeypatch):
    """A temp file and a rename, like every other write here: a cover the note
    already points at is never left half overwritten. The inode is how you can
    tell a replacement from an in-place write."""
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    cover = cfg.attachments_dir / f"{read_note(first.path).id}.jpg"
    before = cover.stat().st_ino

    class Bigger(Jpeg):
        content = b"a different image, longer than the first one"

    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Bigger())
    add(cfg, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    assert cover.read_bytes() == Bigger.content
    assert cover.stat().st_ino != before, "the bytes went into the file in place"


def test_a_cover_does_not_replace_a_link_the_user_made_inside_the_vault(
        cfg, q, monkeypatch):
    """The containment check alone would allow this one: the symlink resolves
    to somewhere inside the folder, and os.replace would put a real file where
    the user's link was. Links are theirs; we write nothing through them and
    nothing over them."""
    extraction(monkeypatch, PAGE)
    cover_fetches(monkeypatch)
    link = link_id(normalize("https://arstechnica.com/vpn"))
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
    real = cfg.attachments_dir / "mi-portada.jpg"
    real.write_bytes(b"the cover I chose myself")
    (cfg.attachments_dir / f"{link}.jpg").symlink_to(real)

    result = add(cfg, "https://arstechnica.com/vpn", queue=q)

    assert (cfg.attachments_dir / f"{link}.jpg").is_symlink()
    assert real.read_bytes() == b"the cover I chose myself"
    assert read_note(result.path).cover is None
