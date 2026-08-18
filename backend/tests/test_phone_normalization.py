import pytest

from app.tools.whatsapp import _normalize_phone


def test_ten_digit_number_gets_default_country_code():
    assert _normalize_phone("9876543210") == "919876543210"


def test_number_that_already_has_a_country_code_is_left_alone():
    assert _normalize_phone("919876543210") == "919876543210"


def test_strips_spaces_dashes_and_plus():
    assert _normalize_phone("+91 98765-43210") == "919876543210"


@pytest.mark.parametrize("bad", ["123", "abcdefghij", "12345678901234567", ""])
def test_rejects_numbers_that_dont_look_real(bad):
    with pytest.raises(ValueError):
        _normalize_phone(bad)
