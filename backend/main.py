"""FastAPI application for the CtoN offline demonstration."""

from __future__ import annotations

import uuid
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import connect, initialize_database, open_database
from .schemas import ApiResponse
from .seed import seed_database
from .poem_service import generate_city_poem
from .services import get_city, get_route, get_weather, get_weather_profile, list_routes
from .weather_service import refresh_active_route_weather
from .external.deepseek_api import DeepSeekError
from .external.qweather_api import QWeatherError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    with open_database() as connection:
        seed_database(connection)
    yield


app = FastAPI(title="CtoN API", version="0.1.0", lifespan=lifespan)
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"], allow_headers=["*"])


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


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exception: HTTPException) -> JSONResponse:
    if exception.status_code == 404:
        data = {"code": 40401, "message": "资源不存在", "data": {}, "request_id": request_id(request)}
        return JSONResponse(status_code=404, content=data)
    return JSONResponse(status_code=exception.status_code, content={"code": exception.status_code * 100, "message": str(exception.detail), "data": {}, "request_id": request_id(request)})


@app.get("/api/v1/health")
def health(request: Request):
    with connect() as connection:
        connection.execute("SELECT 1")
    return response({"status": "ok", "database": "ok", "version": "0.1.0"}, request)


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
def city_weather(city_id: int, request: Request):
    with connect() as connection:
        weather = get_weather(connection, city_id)
    if not weather:
        raise HTTPException(status_code=404)
    return response(weather, request)


@app.post("/api/v1/cities/{city_id}/poem")
def city_poem(city_id: int, request: Request):
    try:
        with connect() as connection:
            poem = generate_city_poem(connection, city_id)
    except DeepSeekError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not poem:
        raise HTTPException(status_code=404)
    return response(poem, request)


@app.get("/api/v1/routes/{route_id}/weather-profile")
def weather_profile(route_id: int, request: Request):
    with connect() as connection:
        profile = get_weather_profile(connection, route_id)
    if not profile:
        raise HTTPException(status_code=404)
    return response(profile, request)


@app.post("/api/v1/weather/refresh")
def refresh_weather(request: Request):
    try:
        with open_database() as connection:
            result = refresh_active_route_weather(connection)
    except QWeatherError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return response(result, request)
