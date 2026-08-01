import httpx

from backend.config import DeepSeekSettings
from backend.external.deepseek_api import DeepSeekClient


def test_deepseek_client_returns_message_content(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "江面收起一盏晚灯"}}]})

    monkeypatch.setattr("backend.external.deepseek_api.httpx.post", fake_post)
    client = DeepSeekClient(DeepSeekSettings(api_key="test-key", base_url="https://api.deepseek.com", model="deepseek-v4-flash"))
    assert client.generate_poem("写诗") == "江面收起一盏晚灯"
