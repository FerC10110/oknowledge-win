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
    """a.co/x//y should normalize with https prepended and path preserved."""
    assert normalize("a.co/x//y") == "https://a.co/x//y"


def test_non_http_schemes_are_returned_unchanged():
    """mailto, javascript, ftp etc. should be returned as-is, stripped."""
    assert normalize("mailto:a@b.com") == "mailto:a@b.com"
    assert normalize("  javascript:alert(1)  ") == "javascript:alert(1)"


def test_malformed_urls_do_not_raise():
    """Invalid URLs should return a string, not raise."""
    # example.com:abc/x has a dot in the prefix, so it tries to normalize
    # and the invalid port causes fallback to return the original input
    bad_url_1 = "example.com:abc/x"
    result_1 = normalize(bad_url_1)
    assert isinstance(result_1, str)
    assert result_1 == bad_url_1  # Fallback returns the stripped original, not with https prepended

    # Empty string should return empty string
    assert normalize("") == ""

    # Whitespace-only should return empty string
    assert normalize("  ") == ""

    # link_id should also work without raising
    id_1 = link_id(bad_url_1)
    id_empty = link_id("")
    assert len(id_1) == 12
    assert len(id_empty) == 12
    assert all(c in "0123456789abcdef" for c in id_1)
    assert all(c in "0123456789abcdef" for c in id_empty)


def test_ipv6_brackets_are_preserved():
    """IPv6 addresses should keep their brackets in the netloc."""
    assert normalize("https://[::1]:8080/x") == "https://[::1]:8080/x"


def test_localhost_with_port():
    """localhost:8080/x should normalize to https://localhost:8080/x."""
    assert normalize("localhost:8080/x") == "https://localhost:8080/x"


def test_hostname_with_port():
    """example.com:8080/path should normalize to https://example.com:8080/path."""
    assert normalize("example.com:8080/path") == "https://example.com:8080/path"


def test_hostname_with_port_and_tracking_params():
    """Tracking params should be stripped even with ports."""
    url = "example.com:8080/path?utm_source=x&id=7"
    normalized = normalize(url)
    assert normalized == "https://example.com:8080/path?id=7"
    # The tracking-param-free version should have the same ID
    assert link_id(url) == link_id("example.com:8080/path?id=7")
