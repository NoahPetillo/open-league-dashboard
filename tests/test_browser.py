"""The browser entry point's own logic: routing requests (straight to ESPN, or through the
relay when there are cookies) and the SWID clean-up."""

from __future__ import annotations

import browser

from league.espn import EspnClient, braced


def test_braced_swid():
    assert braced("ABC-123") == "{ABC-123}"
    assert braced(" {ABC-123} ") == "{ABC-123}"
    assert braced("") is None and braced(None) is None


def test_client_takes_explicit_league():
    c = EspnClient("123", "2025", " s2 ", "ABC")
    assert (c.league_id, c.season, c.espn_s2, c.swid) == (123, 2025, "s2", "{ABC}")
    assert EspnClient(1, 2025, "", "").espn_s2 is None


def test_requests_with_cookies_go_through_the_relay(monkeypatch):
    seen, said = {}, []
    http = browser._Http("https://example.test/api/espn/", said.append)
    monkeypatch.setattr(http.session, "get", lambda url, **kw: seen.update(url=url, **kw))
    http.get(browser.ESPN + "seasons/2026/segments/0/leagues/1", params={"view": "mTeam"},
             cookies={"espn_s2": "s2", "SWID": "{id}"})
    assert seen["url"] == "https://example.test/api/espn/seasons/2026/segments/0/leagues/1"
    assert seen["headers"] == {"x-espn-s2": "s2", "x-espn-swid": "{id}"}
    assert "cookies" not in seen
    assert said == ["Reading your league from ESPN (1)…"]


def test_requests_without_cookies_go_straight_to_espn(monkeypatch):
    seen = {}
    http = browser._Http("https://example.test/api/espn/")
    monkeypatch.setattr(http.session, "get", lambda url, **kw: seen.update(url=url, **kw))
    http.get(browser.ESPN + "seasons/2026/players", headers={"x-fantasy-filter": "{}"}, cookies=None)
    assert seen["url"] == browser.ESPN + "seasons/2026/players"
    assert seen["headers"] == {"x-fantasy-filter": "{}"}


def test_browser_never_sends_headers_the_browser_refuses():
    http = browser._Http("https://example.test/api/espn/")
    assert "Accept-Encoding" not in http.session.headers
    assert "Connection" not in http.session.headers
