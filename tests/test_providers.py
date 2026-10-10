"""The table of who the api engine can be pointed at.

One row per provider, and that row is the only place its address and its
variable name are written down: the engine, the settings page and the help
text all read them from here, so a wrong row is wrong everywhere at once.
These tests are what keeps a row added by hand honest.
"""

from oknowledge.ai.providers import (COMPLETION_SUFFIXES, PROTOCOLS, PROVIDERS,
                                     find, models_url)


# --- the table ----------------------------------------------------------------

def test_every_provider_speaks_a_protocol_the_engine_knows():
    assert {p.protocol for p in PROVIDERS} <= set(PROTOCOLS)


def test_every_address_is_an_endpoint_the_models_url_can_be_derived_from():
    for p in PROVIDERS:
        assert p.url.startswith("https://"), p.id
        assert p.url.endswith(COMPLETION_SUFFIXES), p.id


def test_the_two_providers_that_configs_already_name_are_still_here():
    # A config written before this table existed says provider = "anthropic".
    assert find("anthropic").protocol == "anthropic"
    assert find("openai").protocol == "openai"


def test_no_id_is_repeated():
    ids = [p.id for p in PROVIDERS]
    assert len(set(ids)) == len(ids)


def test_each_provider_says_what_to_call_the_key_and_where_to_get_it():
    for p in PROVIDERS:
        assert p.key_env.isidentifier() and p.key_env.isupper(), p.id
        assert p.console.startswith("https://"), p.id


def test_most_of_them_hand_out_a_key_for_nothing():
    # The reason the list is long: a provider you can try today without a card.
    assert len([p for p in PROVIDERS if p.free]) >= 5


def test_every_provider_says_what_it_will_cost_you():
    # Including the two paid ones. The user who asked for this list believed
    # OpenAI handed out a free API key, and the page is where that gets
    # corrected -- so a row with nothing to say about its price is a defect.
    for p in PROVIDERS:
        assert p.note.strip(), p.id


def test_the_list_is_short_enough_to_read_down():
    # The page shows every row, and a phone shows them one under the other.
    assert len(PROVIDERS) <= 10


def test_every_provider_has_a_name_a_person_can_read():
    for p in PROVIDERS:
        assert p.label == p.label.strip() != ""


def test_there_is_no_such_provider():
    assert find("gopher") is None


# --- where the same server lists its models -----------------------------------

def test_the_models_url_sits_beside_the_endpoint_not_at_the_host_root():
    # Gemini's compatible API lives under a path. Asking the host's root asks
    # a different API, which is what the first version of this did.
    assert models_url(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    ) == "https://generativelanguage.googleapis.com/v1beta/openai/models"


def test_a_gateway_of_your_own_is_asked_under_its_own_path():
    assert models_url("https://gw.example.com/proxy/v1/chat/completions") == (
        "https://gw.example.com/proxy/v1/models")


def test_anthropic_is_asked_beside_its_messages():
    assert models_url("https://api.anthropic.com/v1/messages") == (
        "https://api.anthropic.com/v1/models")


def test_an_address_that_is_not_an_endpoint_at_all_still_gets_a_listing_url():
    assert models_url("https://gw.example.com/v1") == "https://gw.example.com/v1/models"
    assert models_url("https://gw.example.com/v1/") == "https://gw.example.com/v1/models"


def test_a_key_that_travels_in_the_query_travels_to_the_listing_too():
    assert models_url("https://gw.example.com/v1/chat/completions?key=abc") == (
        "https://gw.example.com/v1/models?key=abc")
