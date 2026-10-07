"""Importing a WhatsApp export from the browser.

Two requests: one that reads the file and shows what it found, one that writes.
Most of this file is about the first one writing nothing, and about the token
that carries the upload between them naming nothing but its own staged file.
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.vault import rebuild_indexes
from oknowledge.web.app import create_app

# 18/7 proves the day comes first; the bare domain and the repeat are the two
# cases the preview has to show before anything is written.
EXPORT = """\
18/7/2019, 11:36 - Fer: https://scratux.org/#download
19/7/2019, 09:00 - Fer: mirá https://opencode.ai y después
20/7/2019, 10:00 - Ana: https://opencode.ai otra vez
21/7/2019, 11:00 - Fer: codewars.com
22/7/2019, 12:00 - Ana: ssh late.sh
"""


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    """The staged upload lives under XDG_STATE_HOME: never the real one."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def setup(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


def zipped(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(name, text)
    return buffer.getvalue()


def upload(client, data, name="chat.txt"):
    return client.post("/import", files={"file": (name, data, "text/plain")})


def notes_in(cfg):
    return sorted(p.name for p in cfg.links_dir.glob("*.md"))


def token_in(page: str) -> str:
    before, _, rest = page.partition('name="token" value="')
    assert rest, "the preview carries no token"
    return rest.partition('"')[0]


def staged_files(tmp_path):
    folder = tmp_path / "state" / "oknowledge" / "import"
    return sorted(p.name for p in folder.glob("*")) if folder.is_dir() else []


# --- the first request reads and shows, and writes nothing -------------------

def test_the_upload_page_offers_a_file(setup):
    _, client = setup

    page = client.get("/import").text

    assert 'type="file"' in page


def test_a_txt_export_is_previewed_and_nothing_is_written(setup):
    cfg, client = setup

    page = upload(client, EXPORT).text

    assert 'class="import-preview"' in page
    assert notes_in(cfg) == []


def test_the_zip_whatsapp_hands_you_is_read_too(setup):
    """The export arrives as a .zip; unpacking it by hand was the old price."""
    cfg, client = setup

    page = upload(client, zipped("Chat de WhatsApp.txt", EXPORT), "chat.zip").text

    assert 'class="import-preview"' in page
    assert notes_in(cfg) == []


def test_a_zip_is_recognised_by_its_contents_not_its_name(setup):
    """A browser's filename is whatever the file was called on disk."""
    _, client = setup

    page = upload(client, zipped("export.txt", EXPORT), "chat.txt").text

    assert 'class="import-preview"' in page


def test_the_preview_counts_the_links_and_the_messages(setup):
    _, client = setup

    page = upload(client, EXPORT).text

    assert "4" in page          # four links in five messages
    assert "2019-07-18" in page and "2019-07-21" in page


def test_the_preview_counts_what_would_actually_be_written(setup):
    """Four links, one of them the same link twice: three notes. The number on
    the button is the one the user decides on, so it is deduplicated the way
    the write deduplicates -- by the id the URL normalises to."""
    _, client = setup

    page = upload(client, EXPORT).text

    assert "Import 3 links" in page


def test_the_preview_says_nothing_is_new_the_second_time(setup):
    """Importing the same export twice is the obvious mistake. The preview has
    to say so before the button is pressed, not after."""
    _, client = setup
    client.post("/import/confirm", data={"token": token_in(upload(client, EXPORT).text)})

    page = upload(client, EXPORT).text

    assert "Import 0 links" in page


def test_the_button_does_not_say_one_links(setup):
    """Every other count on this page is a label, which needs no agreement.
    The button is a sentence, so it is the one that needs its singular."""
    _, client = setup
    one = "18/7/2019, 11:36 - Fer: https://scratux.org/ y de nuevo https://scratux.org/\n"

    page = upload(client, one).text

    assert "Import 1 link" in page
    assert "Import 1 links" not in page


def test_the_date_order_is_translated_and_not_printed_raw():
    """It is a value the page prints, not a key somebody typed into a template,
    which is how it stayed English on a Spanish page while every test passed."""
    from oknowledge.i18n import STRINGS

    assert {"day/month", "month/day"} <= set(STRINGS["es"])


def test_the_preview_says_how_it_read_the_dates(setup):
    """Reading them the other way round moves every note to another day, and
    it is the one mistake the written notes do not show."""
    _, client = setup

    page = upload(client, EXPORT).text

    assert "day/month" in page


def test_the_preview_warns_when_the_date_order_was_only_assumed(setup):
    """Every date below 13 fits both readings, so the parser picks one."""
    _, client = setup

    ambiguous = "5/4/2019, 15:11 - Fer: https://opencode.ai\n"
    page = upload(client, ambiguous).text

    assert "import-assumed" in page


def test_the_preview_lists_the_links_written_without_a_scheme(setup):
    """These are the guesses: a sentence ending in a word that happens to be a
    TLD looks exactly like a domain. Seeing them is the point of the preview."""
    _, client = setup

    page = upload(client, EXPORT).text

    assert 'class="import-bare"' in page
    assert "codewars.com" in page


def test_the_preview_shows_what_looked_like_a_link_and_was_not(setup):
    _, client = setup

    page = upload(client, EXPORT).text

    assert "ssh late.sh" in page


# --- the second request writes ----------------------------------------------

def test_confirming_writes_the_notes(setup):
    cfg, client = setup
    token = token_in(upload(client, EXPORT).text)

    page = client.post("/import/confirm", data={"token": token}).text

    assert 'class="import-result"' in page
    assert len(notes_in(cfg)) == 3        # the repeat is one note, not two


def test_confirming_clears_the_staged_upload(setup, tmp_path):
    _, client = setup
    token = token_in(upload(client, EXPORT).text)
    assert staged_files(tmp_path) != []

    client.post("/import/confirm", data={"token": token})

    assert staged_files(tmp_path) == []


def test_confirming_twice_does_not_write_twice(setup):
    """A refresh re-posts the form. The upload is gone, so the second one is
    told so instead of landing a second copy of every note."""
    cfg, client = setup
    token = token_in(upload(client, EXPORT).text)
    client.post("/import/confirm", data={"token": token})
    written = notes_in(cfg)

    again = client.post("/import/confirm", data={"token": token})

    assert notes_in(cfg) == written
    assert 'class="import-result"' not in again.text


def test_the_new_notes_show_up_in_the_library_at_once(setup):
    """End to end: a file chosen in a browser becomes something you can see.

    What makes it work is that every reading route refreshes the index on its
    way in, so the import route does not have to -- which is why this passes
    whether or not it does. It is here for the whole path, not for the refresh.
    """
    _, client = setup
    token = token_in(upload(client, EXPORT).text)

    client.post("/import/confirm", data={"token": token})

    assert "scratux.org" in client.get("/").text


# --- the token names its own file and nothing else ---------------------------

@pytest.mark.parametrize("token", [
    "", "deadbeef", "a" * 32, "../../../../etc/passwd",
    "../queue/abc", "0123456789abcdef0123456789abcdeg",
    "0123456789ABCDEF0123456789ABCDEF", "0123456789abcdef0123456789abcdef0",
    # Begins with the characters a token is made of and leaves anyway. A guard
    # that matches a prefix instead of the whole string lets this one through,
    # and every shape above it still looks refused.
    "abcdef/../../secret", "abcdef0123456789abcdef0123456789/../../secret",
])
def test_a_token_that_names_no_staged_upload_writes_nothing(setup, token):
    cfg, client = setup
    # A real upload first. It is the only state in which a token is ever
    # offered -- and the only one in which the staging folder exists, which is
    # what a traversal needs in order to have somewhere to walk out of. Without
    # it these pass on "no such directory" and prove nothing about the guard.
    upload(client, EXPORT)

    answer = client.post("/import/confirm", data={"token": token})

    assert answer.status_code == 400
    assert notes_in(cfg) == []


@pytest.mark.parametrize("token", ["../secret", "abcdef/../../secret"])
def test_a_token_cannot_reach_a_file_outside_the_staging_folder(setup, tmp_path, token):
    """The token is pasted into a path. A traversal must not even be read.

    The second shape starts with the characters a real token is made of: a
    guard that matches a prefix rather than the whole string refuses the first
    and obeys the second.
    """
    cfg, client = setup
    upload(client, EXPORT)          # the staging folder has to exist to escape it
    outside = tmp_path / "state" / "oknowledge" / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text(EXPORT, encoding="utf-8")

    answer = client.post("/import/confirm", data={"token": token})

    assert answer.status_code == 400
    # Not read, and -- the worse half -- not unlinked by drop() afterwards.
    assert outside.exists()
    assert outside.read_text(encoding="utf-8") == EXPORT
    assert notes_in(cfg) == []


def test_an_absolute_token_does_not_become_the_path(setup, tmp_path):
    """`staging / token` is a pathlib join, and joining an absolute path throws
    the left side away: the token would BE the path. Nothing below the staging
    folder can be named this way, so the guard is what stops it."""
    cfg, client = setup
    upload(client, EXPORT)
    outside = tmp_path / "secret.txt"
    outside.write_text(EXPORT, encoding="utf-8")

    answer = client.post("/import/confirm",
                         data={"token": str(outside)[:-len(".txt")]})

    assert answer.status_code == 400
    assert outside.exists()
    assert notes_in(cfg) == []


# --- what is not an export --------------------------------------------------

def test_a_file_that_is_not_an_export_is_refused_not_a_crash(setup):
    cfg, client = setup

    answer = upload(client, "no soy un export de nada\n")

    assert answer.status_code == 400
    assert "import-problem" in answer.text
    assert notes_in(cfg) == []


def test_a_zip_with_no_text_inside_says_so(setup):
    """The member holds a perfectly good export, so the refusal can only come
    from its name. Reading whatever is in the zip would answer with a preview."""
    _, client = setup

    answer = upload(client, zipped("photo.jpg", EXPORT), "chat.zip")

    assert answer.status_code == 400
    assert "import-problem" in answer.text
    assert "import-preview" not in answer.text


def test_a_zip_that_is_not_one_is_refused(setup):
    _, client = setup

    answer = upload(client, b"PK\x03\x04 and then nothing", "chat.zip")

    assert answer.status_code == 400
    assert "import-problem" in answer.text


def test_an_upload_too_big_to_be_a_chat_is_refused(setup):
    """Six years of chat is 198 KB. Nothing near the cap is a real export, and
    the whole upload is held in memory to be parsed."""
    from oknowledge.web.import_file import MAX_UPLOAD

    cfg, client = setup

    answer = upload(client, b"x" * (MAX_UPLOAD + 1))

    assert answer.status_code == 400
    assert notes_in(cfg) == []


# The two caps, asked of the function that holds them. Through a route they
# cannot be seen: text that long is not a valid export either, so the answer is
# the same 400 whether the cap exists or not, and the test proves nothing.

def test_the_upload_cap_is_what_refuses_a_huge_file():
    from oknowledge.web.import_file import MAX_UPLOAD, BadUpload, text_of

    text_of(b"a" * MAX_UPLOAD)                      # exactly the cap is fine
    with pytest.raises(BadUpload):
        text_of(b"a" * (MAX_UPLOAD + 1))


def test_the_text_cap_is_what_refuses_a_zip_that_unpacks_huge():
    from oknowledge.web.import_file import MAX_TEXT, BadUpload, text_of

    with pytest.raises(BadUpload):
        text_of(zipped("chat.txt", "a" * (MAX_TEXT + 1)))


def test_an_empty_file_is_refused_before_anything_else():
    from oknowledge.web.import_file import BadUpload, text_of

    with pytest.raises(BadUpload):
        text_of(b"")


def test_a_zip_that_unpacks_to_far_more_than_it_weighs_is_refused(setup):
    """A kilobyte of zip can hold a gigabyte of zeroes, and the text is read
    into memory. The bound is on what comes out, not on what was declared."""
    from oknowledge.web.import_file import MAX_TEXT

    _, client = setup

    answer = upload(client, zipped("chat.txt", "x" * (MAX_TEXT + 1)), "chat.zip")

    assert answer.status_code == 400
    assert "import-problem" in answer.text


# --- the staging folder does not fill up ------------------------------------

def test_an_abandoned_upload_is_swept_by_the_next_one(setup, tmp_path):
    """Closing the tab between the two steps leaves the text behind. It is the
    user's chat log: it does not get to sit there forever."""
    import os
    import time

    _, client = setup
    upload(client, EXPORT)
    old = staged_files(tmp_path)
    assert len(old) == 1
    folder = tmp_path / "state" / "oknowledge" / "import"
    stale = folder / old[0]
    long_ago = time.time() - 7200
    os.utime(stale, (long_ago, long_ago))

    upload(client, EXPORT)

    assert old[0] not in staged_files(tmp_path)
    assert len(staged_files(tmp_path)) == 1


def test_a_fresh_upload_is_not_swept(setup, tmp_path):
    _, client = setup
    upload(client, EXPORT)
    first = staged_files(tmp_path)
    # Without this the subset below holds for two empty sets and proves nothing.
    assert len(first) == 1

    upload(client, EXPORT)

    assert set(first) <= set(staged_files(tmp_path))
    assert len(staged_files(tmp_path)) == 2
