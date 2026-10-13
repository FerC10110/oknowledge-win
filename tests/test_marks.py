"""A mark is one emoji you put on a note. These are the rules for what counts."""

import pytest

from oknowledge.marks import DEFAULT_MARKS, clean_mark, rank_marks


@pytest.mark.parametrize("mark", ["⭐", "🔥", "❤️", "👍🏽", "🇦🇷", "👨‍👩‍👧", "📚"])
def test_an_emoji_is_a_mark(mark):
    assert clean_mark(mark) == mark


def test_spaces_around_it_go():
    assert clean_mark("  ⭐ \n") == "⭐"


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_nothing_means_take_the_mark_off(empty):
    assert clean_mark(empty) == ""


@pytest.mark.parametrize("bad", ["a", "ab", "⭐a", "1️⃣", "3", "⭐ ⭐", "!!", "→",
                                 "⭐" * 9, "\x00⭐", "⭐‮"])
def test_anything_else_is_refused(bad):
    assert clean_mark(bad) is None


def test_a_number_from_a_hand_edit_is_refused():
    assert clean_mark(3) is None


def test_the_default_list_passes_its_own_rule():
    assert all(clean_mark(m) == m for m in DEFAULT_MARKS)
    assert len(DEFAULT_MARKS) == 12


class N:
    def __init__(self, mark):
        self.mark = mark


def test_most_used_first_then_the_list_order_then_first_seen():
    notes = [N("👀"), N("⭐"), N("🔥"), N("⭐"), N(""), N("🦄"), N("🔥"), N("🐙")]
    assert rank_marks(notes, DEFAULT_MARKS) == [
        ("⭐", 2), ("🔥", 2), ("👀", 1), ("🦄", 1), ("🐙", 1)]


def test_no_marks_no_list():
    assert rank_marks([N(""), N("")], DEFAULT_MARKS) == []
