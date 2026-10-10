import pytest

from oknowledge import i18n


def test_english_is_the_identity():
    t = i18n.translator("en")
    assert t("Search") == "Search"
    assert t("No results") == "No results"


def test_spanish_translates_what_it_knows_and_passes_through_the_rest():
    t = i18n.translator("es")
    assert t("Search") == "Buscar"
    assert t("Categories") == "Categorías"
    assert t("a string nobody translated") == "a string nobody translated"


# --- one substitution pass (F8) ---------------------------------------------

def test_a_marker_inside_an_argument_is_not_substituted_again():
    """A loop would re-scan its own output and substitute a marker that
    arrived inside an argument -- which is how a translated string gets a
    value it was never given."""
    t = i18n.translator("en")
    assert t("%1 and %2", "%2", "x") == "%2 and x"


def test_a_marker_with_no_argument_is_left_alone():
    t = i18n.translator("en")
    assert t("%1 of %2", 3) == "3 of %2"
    assert t("%0 is not a marker", "x") == "%0 is not a marker"


def test_the_cases_that_tell_one_pass_from_a_loop():
    """A percent sign in the value, the same marker twice, and a two-digit
    marker that is not one: each of the three comes out differently if the
    substitution is a loop."""
    t = i18n.translator("en")
    assert t("%1", "100%") == "100%"
    assert t("%1 %2 %1", "a", "b") == "a b a"
    assert t("%10 links", 1) == "%10 links"


# --- nothing in the table is dead (F10) -------------------------------------

def test_every_translated_string_is_one_the_code_asks_for():
    """A key nobody passes to t() is a translation that can rot without
    anybody noticing. The English key is the lookup, so it has to appear
    somewhere a caller can produce it.

    Whitespace, quotes and backslashes come out of both sides first, so a
    notice written as four concatenated source lines still matches the one
    string it builds.
    """
    import pathlib
    import re

    def squeezed(text):
        return re.sub(r"""[\s"'\\]""", "", text)

    root = pathlib.Path(i18n.__file__).resolve().parent
    files = [p for p in [*root.rglob("*.py"), *root.rglob("*.html")]
             if p.name != "i18n.py"]
    blob = squeezed("\n".join(p.read_text(encoding="utf-8") for p in files))

    unused = [key for key in i18n.STRINGS["es"] if squeezed(key) not in blob]
    assert unused == [], f"declared and never asked for: {unused}"


def test_every_string_a_template_asks_for_has_a_spanish_translation():
    """The mirror of the test above, and the one that catches the defect that
    actually happens: a string added to a page in English and never translated.

    conftest pins the interface to English for the whole suite, so no other
    test renders a Spanish page and a missing translation is invisible --
    until the user switches language and finds half a page still in English.
    Only literal keys are checked: a t() over a variable cannot be read here.
    """
    import pathlib
    import re

    root = pathlib.Path(i18n.__file__).resolve().parent
    asked = set()
    for path in root.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""\bt\(\s*'((?:[^'\\]|\\.)*)'""", text, re.S):
            asked.add(match.group(1).replace("\\'", "'"))

    assert asked, "no t('...') call was found at all: the pattern is wrong"
    missing = sorted(key for key in asked if key not in i18n.STRINGS["es"])
    assert missing == [], f"asked for and never translated: {missing}"
