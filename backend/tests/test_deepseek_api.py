import httpx

from backend.config import DeepSeekSettings
from backend.external.deepseek_api import DeepSeekClient
from backend.travel_advice_validation import validate_travel_advice


def test_deepseek_client_returns_message_content(monkeypatch) -> None:
    sent_payload = None

    def fake_post(*args, **kwargs):
        nonlocal sent_payload
        sent_payload = kwargs["json"]
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "沿线有雨，请携带雨具。"}}]})

    monkeypatch.setattr("backend.external.deepseek_api.httpx.post", fake_post)
    client = DeepSeekClient(DeepSeekSettings(api_key="test-key", base_url="https://api.deepseek.com", model="deepseek-v4-flash"))
    assert client.generate_text("生成建议") == "沿线有雨，请携带雨具。"
    assert sent_payload["max_tokens"] == 400


def test_travel_advice_validation_requires_one_paragraph_of_50_to_100_chinese_characters() -> None:
    assert validate_travel_advice("沿线天气湿热多变，建议穿轻薄透气衣物并及时补水。重庆至恩施段可能有雨，请随身携带雨具。武汉以后注意防晒，空气质量整体适合出行。") is None
    assert validate_travel_advice("沿线有雨，请携带雨具。") is not None
    assert validate_travel_advice("沿线天气湿热多变，建议穿轻薄透气衣物并及时补水。重庆至恩施段可能有雨，请随身携带雨具。武汉以后注意防晒，空气质量整体适合出行。\n请注意安全。") is not None
