"""The look every page shares: the handoff's dark tokens and its fonts."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
FONTS = ("geist-400.woff2", "geist-500.woff2", "geist-600.woff2",
         "geist-mono-400.woff2", "geist-mono-500.woff2")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return TestClient(create_app(Config(vault=vault)))


def test_there_is_no_light_mode_any_more():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in css


def test_the_old_names_point_at_the_handoff_colours():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    assert "--bg: #141519" in root
    assert "--fg: #e7e7ea" in root
    assert "--accent: #a9b4de" in root


def test_every_page_loads_the_new_stylesheet(client):
    body = client.get("/settings").text
    assert '<link rel="stylesheet" href="/static/app.css">' in body


@pytest.mark.parametrize("name", FONTS)
def test_the_fonts_are_served_from_here(client, name):
    answer = client.get(f"/static/fonts/{name}")
    assert answer.status_code == 200
    assert answer.content[:4] == b"wOF2"


def test_the_font_licence_ships_with_the_fonts():
    assert "SIL OPEN FONT LICENSE" in (STATIC / "fonts" / "OFL.txt").read_text(encoding="utf-8").upper()


def test_the_stylesheet_declares_both_families():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert css.count("@font-face") == 5
    assert 'font-family: "Geist Mono"' in css
    assert "font-display: swap" in css
