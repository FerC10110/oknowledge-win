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


def test_ref_parameter_is_preserved():
    """ref is real content, not tracking: github.com/o/r?ref=dev should keep the param."""
    url_with_ref = "https://example.com/page?ref=dev"
    url_without_ref = "https://example.com/page"
    assert normalize(url_with_ref) == url_with_ref
    assert link_id(url_with_ref) != link_id(url_without_ref)


def test_short_host_with_double_slash_in_path():
    """a.co/x//y should not be misparsed as having no scheme."""
    normalized = normalize("a.co/x//y")
    assert normalized.startswith("https://a.co/")


def test_non_http_schemes_are_returned_unchanged():
    """mailto, javascript, ftp etc. should be returned as-is, stripped."""
    assert normalize("mailto:a@b.com") == "mailto:a@b.com"
    assert normalize("  javascript:alert(1)  ") == "javascript:alert(1)"


def test_malformed_urls_do_not_raise():
    """Invalid URLs should return a string, not raise."""
    bad_url_1 = "example.com:abc/x"
    bad_url_2 = ""
    result_1 = normalize(bad_url_1)
    result_2 = normalize(bad_url_2)
    assert isinstance(result_1, str)
    assert isinstance(result_2, str)
    # link_id should also work without raising
    id_1 = link_id(bad_url_1)
    id_2 = link_id(bad_url_2)
    assert len(id_1) == 12
    assert len(id_2) == 12
    assert all(c in "0123456789abcdef" for c in id_1)
    assert all(c in "0123456789abcdef" for c in id_2)


def test_ipv6_brackets_are_preserved():
    """IPv6 addresses should keep their brackets in the netloc."""
    assert normalize("https://[::1]:8080/x") == "https://[::1]:8080/x"
