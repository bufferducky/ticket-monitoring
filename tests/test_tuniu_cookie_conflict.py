"""保存 PC/H5 会话后，同名跨域 Cookie 不应中断查询或制造登录失效证据。"""
import json
import logging
from unittest.mock import Mock

import httpx
import pytest

import crawlers.tuniu as tn


@pytest.mark.parametrize("page_token", ["page-token", ""])
def test_duplicate_mtoken_reaches_list_api(monkeypatch, page_token):
    sent = []

    def respond(request):
        if str(request.url).startswith(tn.LIST_API):
            sent.append(json.loads(request.url.params["d"]))
            return httpx.Response(200, json={"success": True, "data": {"fareList": [
                {"flightPriceList": [{"fareBreakdownList": [
                    {"baseFare": 800, "psgType": "ADT"}]}]}]}})
        return httpx.Response(200, text="")

    client = httpx.Client(transport=httpx.MockTransport(respond))
    c = tn.TuniuCrawler({"rate_limit": False}, logging.getLogger("cookie-test"))
    monkeypatch.setattr(tn._net, "new_client", lambda *a, **k: client)
    monkeypatch.setattr(tn, "_FARE_FLOOR", 1)
    monkeypatch.setattr(c, "_saved_page_token", lambda *a: page_token)
    monkeypatch.setattr(c, "_install_tac_cookies", lambda *a: None)
    monkeypatch.setattr(c, "_saved_session_cookies", lambda: [
        ("mtoken", "api-token", ".tuniu.com"),
        ("mtoken", "pc-token", "flight.tuniu.com"),
    ])

    ok, raw, _ = c._one_attempt("CTU", "SYX", "2026-11-17", polls=1)
    assert ok and raw is not None
    assert sent[0]["tokenKey"] == (page_token or "api-token")


def test_tracking_cookies_respect_api_domain(monkeypatch):
    c = tn.TuniuCrawler({}, logging.getLogger("cookie-test"))
    with httpx.Client() as client:
        for domain, value in [(".tuniu.com", "api"), ("flight.tuniu.com", "pc")]:
            client.cookies.set("udid", value + "-device", domain=domain)
            client.cookies.set("_taca", value + "-login-time", domain=domain)
        monkeypatch.setattr(c, "_fetch_udid", Mock(side_effect=AssertionError("saved udid exists")))
        c._install_tac_cookies(client)
        assert client.cookies.get("_taca", domain=".tuniu.com") == "api-login-time"
        assert client.cookies.get("_taca", domain="flight.tuniu.com") == "pc-login-time"


def test_request_error_does_not_reuse_historical_login_failure(monkeypatch):
    c = tn.TuniuCrawler({"rate_limit": False, "max_attempts": 1},
                         logging.getLogger("cookie-test"))
    monkeypatch.setattr(tn.TuniuCrawler, "login_suspect", True)
    monkeypatch.setattr(c, "_fetch_pc_dom", lambda *a, **k: {})
    monkeypatch.setattr(c, "_saved_page_token", lambda *a: "page-token")
    monkeypatch.setattr(c, "_saved_session_cookies", lambda: [])
    monkeypatch.setattr(c, "_dump_raw", lambda *a: None)
    monkeypatch.setattr(c, "_sleep", lambda: None)

    def fail(*a, **k):
        raise httpx.ConnectError("connection unavailable")

    client = Mock()
    client.get.side_effect = fail
    monkeypatch.setattr(tn._net, "new_client", lambda *a, **k: client)
    assert c.fetch("CTU", "SYX", ["2026-11-17"]) == []
    api_path = next(p for p in c.paths if p["path"] == "H5/API")
    assert api_path["status"] == "error"
    assert "connection unavailable" in api_path["detail"]


def test_debug_directory_failure_does_not_abort_price_processing(tmp_path):
    parent = tmp_path / "file-instead-of-directory"
    parent.write_text("keep")
    c = tn.TuniuCrawler({"debug": True, "debug_dir": str(parent / "debug")},
                         logging.getLogger("cookie-test"))
    c._dump_raw({"success": True, "data": {"salePrice": 800}}, "sample")
    assert parent.read_text() == "keep"
