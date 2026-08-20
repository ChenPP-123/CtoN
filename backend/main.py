"""FastAPI application for the CtoN weather website."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import ApplicationSettings, get_amap_settings, get_application_settings
from .daily_update import (
    UpdateAlreadyRunningError,
    generate_travel_advice_now,
    refresh_weather_now,
    run_daily_update,
)
from .database import connect
from .external.amap_api import AMapError, forward_sdk_request
from .external.deepseek_api import DeepSeekError
from .external.qweather_api import QWeatherError
from .schemas import ApiResponse
from .services import (
    PROFILE_METRICS,
    get_city,
    get_latest_travel_advice,
    get_random_trip,
    get_route,
    get_weather,
    get_weather_profile,
    list_routes,
)
from .time_utils import current_date
from .travel_advice_service import RouteWeatherUnavailableError

APP_VERSION = "1.0.0"
WEATHER_HISTORY_DAYS = 15


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_application_settings()
    yield


def get_documentation_options(settings: ApplicationSettings) -> dict[str, None]:
    return (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if settings.is_production
        else {}
    )


application_settings = get_application_settings()
app = FastAPI(
    title="CtoN API",
    version=APP_VERSION,
    lifespan=lifespan,
    **get_documentation_options(application_settings),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(application_settings.cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
admin_bearer = HTTPBearer(auto_error=False)
cron_bearer = HTTPBearer(auto_error=False)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def request_id(request: Request) -> str:
    return request.state.request_id


def response(data, request: Request) -> ApiResponse:
    return ApiResponse(data=data, request_id=request_id(request))


def resolve_weather_date(requested_date: date | None) -> str:
    today = current_date()
    observation_date = requested_date or today
    earliest_date = today - timedelta(days=WEATHER_HISTORY_DAYS - 1)
    if not earliest_date <= observation_date <= today:
        raise HTTPException(status_code=422, detail="日期只支持最近 15 个自然日")
    return observation_date.isoformat()


def parse_profile_metrics(metrics: str | None) -> tuple[str, ...]:
    if metrics is None:
        return tuple(PROFILE_METRICS)
    requested_metrics = tuple(dict.fromkeys(metric.strip() for metric in metrics.split(",")))
    invalid_metrics = [metric for metric in requested_metrics if metric not in PROFILE_METRICS]
    if invalid_metrics:
        allowed_metrics = ", ".join(PROFILE_METRICS)
        raise HTTPException(
            status_code=422,
            detail=f"metrics 只支持：{allowed_metrics}",
        )
    return requested_metrics


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exception: HTTPException) -> JSONResponse:
    if exception.status_code == 404:
        data = {"code": 40401, "message": "资源不存在", "data": {}, "request_id": request_id(request)}
        return JSONResponse(status_code=404, content=data, headers=exception.headers)
    return JSONResponse(
        status_code=exception.status_code,
        content={"code": exception.status_code * 100, "message": str(exception.detail), "data": {}, "request_id": request_id(request)},
        headers=exception.headers,
    )


def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
) -> None:
    configured_token = get_application_settings().admin_api_token
    if not configured_token:
        raise HTTPException(status_code=503, detail="管理员 API 令牌尚未配置")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, configured_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="管理员凭据无效",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_cron_secret(
    credentials: HTTPAuthorizationCredentials | None = Depends(cron_bearer),
) -> None:
    configured_secret = get_application_settings().cron_secret
    if (
        not configured_secret
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, configured_secret)
    ):
        raise HTTPException(
            status_code=401,
            detail="Cron 凭据无效",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.exception_handler(UpdateAlreadyRunningError)
async def handle_update_already_running(
    request: Request, exception: UpdateAlreadyRunningError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "code": 40901,
            "message": str(exception),
            "data": {},
            "request_id": request_id(request),
        },
    )


@app.get("/api/v1/health")
def health(request: Request):
    with connect() as connection:
        connection.execute("SELECT 1")
    return response({"status": "ok", "database": "ok", "version": APP_VERSION}, request)


@app.get("/_AMapService/{path:path}", include_in_schema=False)
async def amap_service_proxy(path: str, request: Request) -> Response:
    """Proxy only AMap JavaScript SDK service calls so the security code stays server-side."""
    try:
        upstream = await forward_sdk_request(get_amap_settings(), path, list(request.query_params.multi_items()))
    except AMapError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    content_type = upstream.headers.get("content-type", "application/json")
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=content_type)


@app.get("/api/v1/routes")
def routes(request: Request, active_only: bool = True):
    with connect() as connection:
        return response(list_routes(connection, active_only), request)


@app.get("/api/v1/routes/{route_id}")
def route_detail(route_id: int, request: Request):
    with connect() as connection:
        route = get_route(connection, route_id)
    if not route:
        raise HTTPException(status_code=404)
    return response(route, request)


@app.get("/api/v1/cities/{city_id}")
def city_detail(city_id: int, request: Request):
    with connect() as connection:
        city = get_city(connection, city_id)
    if not city:
        raise HTTPException(status_code=404)
    return response(city, request)


@app.get("/api/v1/cities/{city_id}/weather")
def city_weather(
    city_id: int,
    request: Request,
    observation_date: date | None = Query(default=None, alias="date"),
):
    selected_date = resolve_weather_date(observation_date) if observation_date else None
    with connect() as connection:
        weather = get_weather(connection, city_id, selected_date)
    if not weather:
        raise HTTPException(status_code=404)
    return response(weather, request)


@app.get("/api/v1/routes/{route_id}/weather-profile")
def weather_profile(
    route_id: int,
    request: Request,
    observation_date: date | None = Query(default=None, alias="date"),
    metrics: str | None = None,
):
    selected_date = resolve_weather_date(observation_date)
    selected_metrics = parse_profile_metrics(metrics)
    with connect() as connection:
        profile = get_weather_profile(connection, route_id, selected_date, selected_metrics)
    if not profile:
        raise HTTPException(status_code=404)
    return response(profile, request)


@app.get("/api/v1/routes/{route_id}/random-trip")
def random_trip(
    route_id: int,
    request: Request,
    observation_date: date | None = Query(default=None, alias="date"),
):
    selected_date = resolve_weather_date(observation_date)
    with connect() as connection:
        trip = get_random_trip(connection, route_id, selected_date)
    if not trip:
        raise HTTPException(status_code=404)
    return response(trip, request)


@app.get("/api/v1/routes/{route_id}/travel-advice")
def travel_advice(route_id: int, request: Request):
    with connect() as connection:
        if not get_route(connection, route_id):
            raise HTTPException(status_code=404)
        advice = get_latest_travel_advice(connection, route_id)
    return response(advice, request)


@app.post(
    "/api/v1/routes/{route_id}/travel-advice",
    dependencies=[Depends(require_admin_token)],
)
def create_travel_advice(route_id: int, request: Request):
    try:
        advice = generate_travel_advice_now(route_id)
    except LookupError as error:
        raise HTTPException(status_code=404) from error
    except RouteWeatherUnavailableError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DeepSeekError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return response(advice, request)


@app.post("/api/v1/weather/refresh", dependencies=[Depends(require_admin_token)])
def refresh_weather(request: Request):
    try:
        result = refresh_weather_now()
    except QWeatherError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return response(result, request)


@app.get(
    "/api/v1/internal/daily-update",
    dependencies=[Depends(require_cron_secret)],
    include_in_schema=False,
)
def daily_update(request: Request, http_response: Response):
    result = run_daily_update()
    http_response.status_code = {
        "partial": 207,
        "failed": 500,
    }.get(result["status"], 200)
    return response(result, request)
