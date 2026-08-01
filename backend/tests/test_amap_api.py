import asyncio

from backend.config import AMapSettings
from backend.external.amap_api import forward_sdk_request


def test_sdk_proxy_injects_security_code_without_exposing_it_to_callers(monkeypatch) -> None:
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params):
            requests.append((url, params))
            return FakeResponse()

    monkeypatch.setattr("backend.external.amap_api.httpx.AsyncClient", lambda **_: FakeClient())
    asyncio.run(forward_sdk_request(AMapSettings(web_service_key="", security_js_code="server-only"), "v3/vectormap", [("key", "browser-key")]))
    assert requests == [("https://restapi.amap.com/v3/vectormap", [("key", "browser-key"), ("jscode", "server-only")])]


def test_sdk_proxy_reports_missing_security_configuration() -> None:
    from backend.external.amap_api import AMapError

    try:
        asyncio.run(forward_sdk_request(AMapSettings(web_service_key="", security_js_code=""), "v3/vectormap", []))
    except AMapError as error:
        assert "AMAP_SECURITY_JS_CODE" in str(error)
    else:
        raise AssertionError("expected AMapError")
