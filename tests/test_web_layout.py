"""The pages at phone width: what has to be in the HTML and the CSS for it."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import WEB, create_app

LINK = "aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=["vpn"], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def css():
    return WEB.joinpath("static", "style.css").read_text(encoding="utf-8")


# --- the header -------------------------------------------------------------

def test_the_paste_box_folds_into_a_plus(client):
    body = client.get("/").text
    assert re.search(r'<details class="paste" open>\s*<summary[^>]*>＋</summary>', body)
    assert 'action="/add"' in body


def test_saving_everything_is_called_complete_not_all():
    from oknowledge.i18n import STRINGS
    assert STRINGS["es"]["Full"] == "Completo"


def test_every_page_loads_the_layout_script(client):
    assert '<script src="/static/layout.js"></script>' in client.get("/").text


def test_the_layout_script_closes_and_unfocuses_on_a_phone():
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert "(max-width: 42rem)" in js
    assert "details.filters" in js and "details.paste" in js and "blur" in js
