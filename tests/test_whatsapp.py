"""The WhatsApp export parser. No disk, no network: text to list.

Most of this is about what the real file has and the clean example does not:
invisible marks, Windows line endings, split messages. A regex written
against tidy text finds zero messages in the real file.
"""

import pytest

from oknowledge.whatsapp import BadExport, find_links, messages, parse

REAL = """\
18/7/2019, 11:36 - Fer: https://scratux.org/#download
23/7/2019, 11:39 - Fer: sudo chkrootkit
21/7/2019, 13:50 - Fer: "Easy DevOps" by George Seif https://link.medium.com/JfoglQ1zvY
"""


def test_the_real_export_lines_are_read():
    found, day_first, assumed = messages(REAL)

    assert [(m.sent, m.sender) for m in found] == [
        ("2019-07-18", "Fer"), ("2019-07-23", "Fer"), ("2019-07-21", "Fer")]
    assert found[1].text == "sudo chkrootkit"
    assert (day_first, assumed) == (True, False)


def test_a_two_digit_year_is_this_century():
    found, _, _ = messages("14/3/25, 21:07 - Fer: hola\n")

    assert found[0].sent == "2025-03-14"


def test_a_message_split_over_lines_stays_one_message():
    """A link split over two lines does not split."""
    found, _, _ = messages(
        "18/7/2019, 11:36 - Fer: mirá esto\nsegunda línea\n"
        "19/7/2019, 09:00 - Fer: otro\n")

    assert len(found) == 2
    assert found[0].text == "mirá esto\nsegunda línea"


def test_a_system_line_has_no_sender_and_is_still_read():
    """A link inside a system message is still a link."""
    found, _, _ = messages("18/7/2019, 11:36 - Fer creó el grupo\n")

    assert found[0].sender == ""
    assert found[0].text == "Fer creó el grupo"


def test_the_invisible_marks_whatsapp_puts_in_do_not_hide_every_message():
    """U+200E and hard spaces are what the real file carries.

    Without cleaning them, the regex finds zero messages: silent and total.
    The sender split breaks if NBSP or NNBSP replace the space after ":".
    """
    found, _, _ = messages(
        "\u200e18/7/2019, 11:36 - Fer:\xa0https://e.com/x\n"
        "18/7/2019, 11:36 - Foo:\u202fbar\n")

    assert len(found) == 2
    assert found[0].sent == "2019-07-18"
    assert found[0].sender == "Fer"
    assert found[0].text == "https://e.com/x"
    assert found[1].sender == "Foo"
    assert found[1].text == "bar"


def test_windows_line_endings_and_a_bom_are_read():
    found, _, _ = messages("\ufeff18/7/2019, 11:36 - Fer: hola\r\n")

    assert len(found) == 1
    assert found[0].text == "hola"


def test_day_first_is_detected_from_a_day_over_twelve():
    _, day_first, assumed = messages("18/7/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (True, False)


def test_month_first_is_detected_from_a_second_field_over_twelve():
    found, day_first, assumed = messages("7/18/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (False, False)
    assert found[0].sent == "2019-07-18"


def test_an_ambiguous_file_assumes_day_first_and_says_so():
    """An export of less than 13 days has no evidence. Assume and report."""
    _, day_first, assumed = messages("7/8/2019, 11:36 - Fer: x\n")

    assert (day_first, assumed) == (True, True)


def test_a_file_that_contradicts_itself_is_refused():
    with pytest.raises(BadExport) as raised:
        messages("18/7/2019, 11:36 - Fer: x\n7/18/2019, 11:36 - Fer: y\n")

    assert "18/7/2019" in str(raised.value)
    assert "7/18/2019" in str(raised.value)


def test_a_file_with_no_recognisable_line_names_the_format_it_wanted():
    with pytest.raises(BadExport) as raised:
        messages("esto no es un export\nni esto tampoco\n")

    assert "D/M/YYYY" in str(raised.value)
    assert "esto no es un export" in str(raised.value)


def test_an_empty_file_is_refused_too():
    with pytest.raises(BadExport):
        messages("")


def test_an_impossible_date_is_skipped_not_fatal():
    """31/2 does not exist. A bad line does not bring down the file."""
    found, _, _ = messages("31/2/2019, 11:36 - Fer: x\n18/7/2019, 11:36 - Fer: y\n")

    assert [m.text for m in found] == ["y"]


@pytest.mark.parametrize("text,expected", [
    # full
    ("https://scratux.org/#download", [("https://scratux.org/#download", False)]),
    ("http://viejo.example.com/x", [("http://viejo.example.com/x", False)]),
    # bare, and they count
    ("youtu.be/abc", [("https://youtu.be/abc", True)]),
    ("scratux.org", [("https://scratux.org", True)]),
    ("www.foo.com", [("https://www.foo.com", True)]),
    ("example.py/docs", [("https://example.py/docs", True)]),
    # bare, and they do not
    ("script.py", []),
    ("README.md", []),
    ("config.json", []),
    ("version 3.10", []),
    ("fer@gmail.com", []),
    ("juan.co@gmail.com", []),
    ("ana.me@x.org", []),
    ("v1.io2", []),
    ("sudo chkrootkit", []),
    ("11 5555-5555", []),
])
def test_what_counts_as_a_link(text, expected):
    assert find_links(text) == expected


def test_a_url_with_balanced_parens_is_not_cut():
    """Wikipedia puts parentheses in the URL and they are part of the link."""
    url = "https://es.wikipedia.org/wiki/Python_(lenguaje)"

    assert find_links(f"mirá {url}") == [(url, False)]


def test_a_url_inside_parens_loses_only_the_closing_one():
    assert find_links("(https://e.com/x)") == [("https://e.com/x", False)]


@pytest.mark.parametrize("text,expected", [
    ("mirá github.com/y.", [("https://github.com/y", True)]),
    ("“e.com/z”", [("https://e.com/z", True)]),
    ("e.com/w, y nada más", [("https://e.com/w", True)]),
    ("https://e.com/v!", [("https://e.com/v", False)]),
])
def test_punctuation_stuck_to_the_end_is_not_part_of_the_link(text, expected):
    assert find_links(text) == expected


def test_two_links_in_one_message_are_both_found():
    assert find_links("foo.com, bar.org/x") == [
        ("https://foo.com", True), ("https://bar.org/x", True)]


def test_two_full_urls_with_no_space_between_them_are_both_found():
    assert find_links("https://a.com,https://b.org") == [
        ("https://a.com", False), ("https://b.org", False)]


def test_two_full_urls_separated_by_a_semicolon_are_both_found():
    assert find_links("https://a.com;https://b.org") == [
        ("https://a.com", False), ("https://b.org", False)]


def test_a_url_that_contains_another_url_is_not_split():
    url = "https://web.archive.org/web/2020/https://example.com/a"

    assert find_links(url) == [(url, False)]


def test_a_link_that_is_a_prefix_of_another_does_not_corrupt_the_comment():
    scan = parse("18/7/2019, 11:36 - Fer: foo.com, foo.com/x\n")

    assert [link.comment for link in scan.links] == [",", ","]
    assert [link.raw for link in scan.links] == ["foo.com", "foo.com/x"]


def test_a_bare_domain_inside_a_full_url_is_not_counted_twice():
    assert find_links("https://github.com/a/b") == [("https://github.com/a/b", False)]


def test_the_comment_is_the_message_without_the_links():
    scan = parse('21/7/2019, 13:50 - Fer: “Easy DevOps” by George Seif '
                 'https://link.medium.com/JfoglQ1zvY\n')

    assert scan.links[0].comment == "“Easy DevOps” by George Seif"
    assert scan.links[0].url == "https://link.medium.com/JfoglQ1zvY"
    assert scan.links[0].sent == "2019-07-21"
    assert scan.links[0].sender == "Fer"
    assert scan.links[0].bare is False


def test_a_message_that_is_only_a_link_has_no_comment():
    scan = parse("18/7/2019, 11:36 - Fer: https://e.com/x\n")

    assert scan.links[0].comment == ""


def test_the_raw_link_is_kept_for_the_dry_run():
    scan = parse("18/7/2019, 11:36 - Fer: mirá youtu.be/abc\n")

    assert scan.links[0].raw == "youtu.be/abc"
    assert scan.links[0].url == "https://youtu.be/abc"
    assert scan.links[0].bare is True


def test_a_message_with_no_link_is_not_imported():
    scan = parse("23/7/2019, 11:39 - Fer: sudo chkrootkit\n")

    assert scan.links == []
    assert scan.messages == 1


def test_a_message_that_looks_like_it_had_a_link_is_reported():
    """The list that exposes a lost link, instead of losing it quietly."""
    scan = parse("23/7/2019, 11:39 - Fer: mirá el config.json que te mandé\n")

    assert scan.links == []
    assert scan.suspicious == ["mirá el config.json que te mandé"]


def test_plain_text_with_no_dots_is_not_suspicious():
    scan = parse("23/7/2019, 11:39 - Fer: sudo chkrootkit\n")

    assert scan.suspicious == []


def test_the_scan_carries_the_date_order_through():
    scan = parse("7/8/2019, 11:36 - Fer: e.com\n")

    assert (scan.day_first, scan.assumed) == (True, True)


# --- what the real 3309-line export turned up --------------------------------


def test_a_percent_encoded_url_is_not_captured_mangled():
    """Line 398 of the real file. `%2F` leaves its `2F` glued to the host, and
    `2Fudemycoupons.me` is a domain that does not exist: not a false positive
    but a link the user did send, saved pointing somewhere else.
    """
    assert find_links("https%3A%2F%2Fudemycoupons.me") == []


def test_a_percent_encoded_url_is_reported_instead_of_captured_wrong():
    """A non-capture the user is told about beats a wrong capture: MAYBE still
    matches the message, so it shows up and gets pasted back by hand once."""
    scan = parse("18/7/2019, 11:36 - Fer: https%3A%2F%2Fudemycoupons.me\n")

    assert scan.links == []
    assert scan.suspicious == ["https%3A%2F%2Fudemycoupons.me"]


def test_the_tracker_list_of_a_magnet_link_captures_nothing():
    """Three of the four mangled captures in the real file came from one magnet
    link's trackers, and there the right answer is to capture nothing. It is
    also why the percent-encoding is not decoded instead: decoding would turn
    these into three junk notes.
    """
    assert find_links(
        "magnet:?xt=urn:btih:abc"
        "&tr=http%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
        "&tr=udp%3A%2F%2Fexplodie.org%3A6969") == []


@pytest.mark.parametrize("url", [
    "https://www.mites.gob.es/ficheros/Guia%20de%20uso.pdf",
    "https://link.trustwallet.com/open_url?coin_id=60&url=https%3A%2F%2Fapp.uniswap.org",
])
def test_percent_encoding_inside_a_real_url_survives_whole(url):
    """The same export carries both of these, and in both the percent signs are
    part of what the user sent. The other half of the rule above."""
    assert find_links(url) == [(url, False)]


@pytest.mark.parametrize("text,expected", [
    ("radio.garden", [("https://radio.garden", True)]),
    ("real.fun", [("https://real.fun", True)]),
])
def test_a_tld_the_curated_list_was_missing(text, expected):
    """Lines 3267-3268 of the real file, two consecutive messages the user
    typed by hand. Both are real sites, and both were lost."""
    assert find_links(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("foo.com:80/x", [("https://foo.com:80/x", True)]),
    ("e.com:3000/panel", [("https://e.com:3000/panel", True)]),
])
def test_a_bare_host_with_a_port_keeps_both_the_port_and_the_path(text, expected):
    """Without the port the path went too, and `foo.com:80/x` was saved as
    `foo.com`: the real target recorded nowhere, and not even suspicious,
    because a link was found. A silent wrong capture, like the mangled
    percent-encoding above."""
    assert find_links(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("mirá e.com: está caído", [("https://e.com", True)]),
    ("e.com:/x", [("https://e.com", True)]),
    ("script.py:42", []),
])
def test_what_follows_a_host_is_only_a_port_when_it_is_digits(text, expected):
    """The other half: a colon ending a sentence, a colon with nothing after
    it, and the `file:line` of a traceback are not ports."""
    assert find_links(text) == expected


@pytest.mark.parametrize("text", ["https://.", "https://", "mirá https://. y chau",
                                  "https://?x", "https://#"])
def test_a_scheme_with_no_host_left_is_not_a_link(text):
    """The bare `"https://"` case guards the regex, not the trim: the FULL
    pattern already needs a character after `://`, and it must stay that way.

    `https://.` trims its dot and leaves `https://`, which is truthy, so it
    was captured and normalize() turned it into `https:///`: a junk note."""
    assert find_links(text) == []


def test_a_system_line_whose_own_text_holds_the_first_colon_keeps_that_text():
    """Everything before the first ": " becomes the sender and is dropped from
    the message, so this line yielded a sender of `Fer cambió el asunto a
    "Links` and a comment of `"`. Spec-conformant, and it throws the user's
    words away."""
    scan = parse('18/7/2019, 11:36 - Fer cambió el asunto a "Links: '
                 'https://e.com/x"\n')

    assert [one.url for one in scan.links] == ["https://e.com/x"]
    assert scan.links[0].sender == ""
    assert "cambió el asunto" in scan.links[0].comment


def test_a_link_inside_a_dropped_sender_prefix_is_not_lost():
    """The same bug where it costs a link: the dropped part is not scanned for
    links and not offered as suspicious either, so this one vanished with no
    trace -- which the never-lose-a-link rule does not allow."""
    scan = parse('18/7/2019, 11:36 - Fer cambió el asunto a '
                 '"https://e.com/x, mirá: esto"\n')

    assert [one.url for one in scan.links] == ["https://e.com/x"]


@pytest.mark.parametrize("line,sender", [
    ("18/7/2019, 11:36 - Juan Pérez: mirá https://e.com/x", "Juan Pérez"),
    ("18/7/2019, 11:36 - +54 9 11 5555-5555: https://e.com/x", "+54 9 11 5555-5555"),
    ("18/7/2019, 11:36 - Fer: https://e.com/x", "Fer"),
])
def test_a_real_sender_is_still_read_as_the_sender(line, sender):
    """The other half: a saved contact, an unsaved number, a one-word name."""
    scan = parse(line + "\n")

    assert scan.links[0].sender == sender


def test_every_contradicting_line_is_named_not_just_the_first_pair():
    """One pasted fragment vetoes all 1215 links, and --dry-run is no escape
    because parse() raises first. Naming one pair at a time costs the user one
    import, one edit and one re-run per stray line."""
    with pytest.raises(BadExport) as raised:
        messages("18/7/2019, 11:36 - Fer: x\n"
                 "7/18/2019, 11:36 - Fer: y\n"
                 "8/19/2019, 11:36 - Fer: z\n")

    said = str(raised.value)
    assert "7/18/2019" in said
    assert "8/19/2019" in said


def test_the_contradiction_says_the_file_can_be_edited():
    """The way out, in the message that blocks the way in."""
    with pytest.raises(BadExport) as raised:
        messages("18/7/2019, 11:36 - Fer: x\n7/18/2019, 11:36 - Fer: y\n")

    assert "edit" in str(raised.value).lower()


def test_a_line_with_both_fields_over_twelve_is_evidence_of_nothing():
    """It read as both sides of the contradiction at once, so the error named
    one line as contradicting itself. No reading of it is a date, which is
    what makes it a bad line and not a bad file."""
    found, day_first, _ = messages("18/13/2019, 11:36 - Fer: x\n"
                                   "19/7/2019, 11:36 - Fer: y\n")

    assert [m.text for m in found] == ["y"]
    assert day_first is True
