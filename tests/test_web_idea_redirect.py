"""An idea has one page, its screen (spec §1, "Lo que se va")."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


def put(cfg):
    note = new_idea("Una vpn.", "VPN", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_an_idea_s_old_address_opens_its_screen(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/ideas/{note.id}"


def test_the_redirect_carries_the_notice(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}?notice=moved&n=2&m=1",
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/ideas/{note.id}?notice=moved&n=2&m=1"


def test_a_write_without_javascript_ends_on_the_screen(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/mine/state",
                                              data={"state": "doing"})
    assert answer.status_code == 200
    assert str(answer.url).endswith(f"/ideas/{note.id}?notice=saved")


@pytest.mark.parametrize("name", ["idea-links.js"])
def test_the_old_script_is_not_served(cfg, name):
    assert TestClient(create_app(cfg)).get(f"/static/{name}").status_code == 404


def test_the_old_templates_are_gone():
    from importlib.resources import files
    templates = files("oknowledge.web").joinpath("templates")
    for name in ("idea-link-results.html", "link-card.html", "ideas.html"):
        assert not templates.joinpath(name).is_file()
