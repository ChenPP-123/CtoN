"""Small AMap adapter for one-off station coordinate verification and SDK proxying."""

from __future__ import annotations

from typing import Any

import httpx2 as httpx

from ..config import AMapSettings


class AMapError(RuntimeError):
    """AMap did not return a usable response."""


class AMapClient:
    """Use only while maintaining the fixed station seed data, never per page view."""

    def __init__(self, settings: AMapSettings) -> None:
        if not settings.is_web_service_configured:
            raise AMapError("未配置 AMAP_WEB_SERVICE_KEY")
        self.settings = settings

    def search_place(self, keywords: str, city: str) -> list[dict[str, Any]]:
        payload = self._get("/v3/place/text", {"keywords": keywords, "city": city})
        pois = payload.get("pois")
        return [poi for poi in pois if isinstance(poi, dict)] if isinstance(pois, list) else []

    def geocode(self, address: str, city: str) -> list[dict[str, Any]]:
        payload = self._get("/v3/geocode/geo", {"address": address, "city": city})
        geocodes = payload.get("geocodes")
        return [item for item in geocodes if isinstance(item, dict)] if isinstance(geocodes, list) else []

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.settings.base_url}{path}",
                params={**params, "key": self.settings.web_service_key},
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AMapError(f"高德地图请求失败：{error}") from error
        if payload.get("status") != "1":
            raise AMapError(f"高德地图返回错误：{payload.get('info', '未知错误')}")
        return payload


async def forward_sdk_request(
    settings: AMapSettings, path: str, query_params: list[tuple[str, str]]
) -> httpx.Response:
    """Forward an AMap JS SDK service request while keeping the security code private."""
    if not settings.is_security_proxy_configured:
        raise AMapError("未配置 AMAP_SECURITY_JS_CODE")
    if not path or ".." in path.split("/"):
        raise AMapError("无效的高德服务路径")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.base_url}/{path.lstrip('/')}",
                params=[*query_params, ("jscode", settings.security_js_code)],
            )
            response.raise_for_status()
            return response
    except httpx.HTTPError as error:
        raise AMapError(f"高德地图服务请求失败：{error}") from error
