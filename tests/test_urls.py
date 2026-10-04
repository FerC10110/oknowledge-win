from oknowledge.urls import link_id, normalize


def test_tracking_fragment_and_case_do_not_change_the_id():
    # El mismo artículo compartido por WhatsApp y copiado del navegador.
    dirty = "HTTPS://WWW.Example.com/Post/?utm_source=wa&utm_medium=x&id=7#intro"
    clean = "https://example.com/Post?id=7"
    assert normalize(dirty) == clean
    assert link_id(dirty) == link_id(clean)


def test_the_youtube_video_id_survives_but_the_share_token_does_not():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=AbC123"
    assert normalize(url) == "https://youtube.com/watch?v=dQw4w9WgXcQ"


def test_different_pages_get_different_ids():
    assert link_id("https://example.com/a") != link_id("https://example.com/b")


def test_the_order_of_the_query_does_not_matter():
    assert normalize("https://e.com/x?b=2&a=1") == normalize("https://e.com/x?a=1&b=2")


def test_the_id_is_twelve_hex_characters():
    value = link_id("https://example.com/")
    assert len(value) == 12
    assert all(c in "0123456789abcdef" for c in value)


def test_a_url_without_scheme_is_assumed_https():
    assert normalize("example.com/post") == "https://example.com/post"


def test_the_root_path_keeps_its_slash():
    assert normalize("https://example.com/") == "https://example.com/"
