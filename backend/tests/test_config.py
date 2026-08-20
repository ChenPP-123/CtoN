import pytest

from backend.config import get_application_settings
from backend.main import get_documentation_options


PRODUCTION_TOKEN = "a" * 32
CRON_SECRET = "b" * 32


def configure_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_API_TOKEN", PRODUCTION_TOKEN)
    monkeypatch.setenv("CRON_SECRET", CRON_SECRET)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example-pooler.ap-southeast-1.aws.neon.tech/cton?sslmode=require",
    )
    monkeypatch.setenv("CORS_ORIGINS", "https://cton.example.com")
    monkeypatch.setenv("QWEATHER_API_KEY", "qweather-key")
    monkeypatch.setenv("QWEATHER_BASE_URL", "https://example.qweather.com")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AMAP_SECURITY_JS_CODE", "amap-security-code")


def test_production_configuration_disables_api_documentation(monkeypatch) -> None:
    configure_production(monkeypatch)

    options = get_documentation_options(get_application_settings())

    assert options == {"docs_url": None, "redoc_url": None, "openapi_url": None}


@pytest.mark.parametrize("token", ["", "too-short", " " * 32])
def test_production_rejects_missing_or_weak_admin_token(monkeypatch, token) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv("ADMIN_API_TOKEN", token)

    with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
        get_application_settings()


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "http://cton.example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://intranet",
        "https://cton.example.com/",
    ],
)
def test_production_rejects_unsafe_cors_origins(monkeypatch, origins) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", origins)

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        get_application_settings()


def test_production_accepts_multiple_https_origins(monkeypatch) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://cton.example.com, https://www.cton.example.com"
    )

    settings = get_application_settings()

    assert settings.cors_origins == (
        "https://cton.example.com",
        "https://www.cton.example.com",
    )


def test_production_accepts_empty_cors_for_same_origin_rewrites(monkeypatch) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "")

    assert get_application_settings().cors_origins == ()


@pytest.mark.parametrize(
    ("name", "value", "error_name"),
    [
        ("CRON_SECRET", "short", "CRON_SECRET"),
        ("DATABASE_URL", "postgresql://db.example.com/cton", "池化"),
        (
            "DATABASE_URL",
            "postgresql://user:pass@example-pooler.neon.tech/cton",
            "sslmode=require",
        ),
        ("QWEATHER_API_KEY", "", "QWEATHER"),
        ("QWEATHER_BASE_URL", "http://weather.example.com", "HTTPS"),
        ("DEEPSEEK_API_KEY", "", "DeepSeek"),
        ("DEEPSEEK_BASE_URL", "http://deepseek.example.com", "HTTPS"),
        ("AMAP_SECURITY_JS_CODE", "", "AMAP_SECURITY_JS_CODE"),
    ],
)
def test_production_rejects_missing_runtime_configuration(
    monkeypatch, name, value, error_name
) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=error_name):
        get_application_settings()


def test_production_requires_distinct_admin_and_cron_tokens(monkeypatch) -> None:
    configure_production(monkeypatch)
    monkeypatch.setenv("CRON_SECRET", PRODUCTION_TOKEN)

    with pytest.raises(ValueError, match="必须与"):
        get_application_settings()
