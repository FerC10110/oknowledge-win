"""An action's section as the idea's screen draws it: cards, not a list."""

from oknowledge.web.markup import section_cards


def test_improvements_are_title_and_detail_under_the_links_line():
    part = section_cards("*Con 2 links: A · B.*\n\n- **Débil** — el arreglo.\n- **Otra** — otro.")
    assert str(part.used) == "Con 2 links: A · B."
    assert [(str(a), str(b)) for a, b in part.cards] == [("Débil", "el arreglo."), ("Otra", "otro.")]
    assert part.lead == [] and part.tail == []


def test_a_finding_keeps_its_link_and_the_lines_around_it():
    part = section_cards("**Ya existe.** Buscado el 2026-10-13 con fake.\n\n"
                         "- [Tailscale](https://tailscale.com) — VPN sobre WireGuard.\n\n"
                         "**Lo tuyo:** para la familia.")
    assert [str(x) for x in part.lead] == ["<strong>Ya existe.</strong> Buscado el 2026-10-13 con fake."]
    title, detail = part.cards[0]
    assert str(title) == '<a href="https://tailscale.com" target="_blank" rel="noreferrer">Tailscale</a>'
    assert str(detail) == "VPN sobre WireGuard."
    assert [str(x) for x in part.tail] == ["<strong>Lo tuyo:</strong> para la familia."]


def test_an_expansion_point_is_a_card_with_no_detail():
    part = section_cards("- Compartir fotos.\n- Bloquear publicidad.")
    assert [(str(a), str(b)) for a, b in part.cards] == [("Compartir fotos.", ""),
                                                         ("Bloquear publicidad.", "")]


def test_nothing_is_an_empty_section():
    part = section_cards("")
    assert (part.used, part.lead, part.cards, part.tail) == (None, [], [], [])


def test_model_text_is_still_escaped():
    title, _ = section_cards("- <img src=x> — y").cards[0]
    assert "<img" not in str(title)
