"""bathingWaterId extraction from raw ids and URLs."""

from hav_badvatten.api import extract_bath_id

REF = "SE0110180000007461"


def test_plain_id():
    assert extract_bath_id(REF) == REF


def test_lowercase_is_upcased():
    assert extract_bath_id(REF.lower()) == REF


def test_doppkartan_site_url():
    assert extract_bath_id(f"https://www.doppkartan.se/?site={REF}") == REF


def test_karta_deep_link():
    url = f"https://badplatsen.havochvatten.se/badplatsen/karta/#/bath/{REF}"
    assert extract_bath_id(url) == REF


def test_surrounding_whitespace():
    assert extract_bath_id(f"  {REF} ") == REF


def test_none_and_garbage():
    assert extract_bath_id(None) is None
    assert extract_bath_id("") is None
    assert extract_bath_id("not an id") is None
