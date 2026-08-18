import pytest

from app.tools.apps import _fuzzy_match

CANDIDATES = ["Notepad", "Google Chrome", "Microsoft Edge", "Spotify"]


def test_exact_match():
    assert _fuzzy_match("Notepad", CANDIDATES) == "Notepad"


def test_case_insensitive_match():
    assert _fuzzy_match("notepad", CANDIDATES) == "Notepad"


def test_short_query_matches_by_substring_not_by_ratio():
    # Regression: difflib.get_close_matches alone picks "Notepad" for "edge"
    # (its whole-string ratio scores a short unrelated name higher than a
    # longer name that actually contains the query) — substring must win.
    assert _fuzzy_match("edge", CANDIDATES) == "Microsoft Edge"
    assert _fuzzy_match("chrome", CANDIDATES) == "Google Chrome"


def test_typo_falls_back_to_fuzzy_ratio():
    assert _fuzzy_match("Notepd", CANDIDATES) == "Notepad"
    assert _fuzzy_match("spotfy", CANDIDATES) == "Spotify"


def test_no_match_raises_lookup_error():
    with pytest.raises(LookupError):
        _fuzzy_match("some totally unrelated application", CANDIDATES)
