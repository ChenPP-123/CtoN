import httpx

from backend.config import DeepSeekSettings
from backend.external.deepseek_api import DeepSeekClient
from backend.poem_service import _is_regulated_poem


def test_deepseek_client_returns_message_content(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "江面收起一盏晚灯"}}]})

    monkeypatch.setattr("backend.external.deepseek_api.httpx.post", fake_post)
    client = DeepSeekClient(DeepSeekSettings(api_key="test-key", base_url="https://api.deepseek.com", model="deepseek-v4-flash"))
    assert client.generate_poem("写诗") == "江面收起一盏晚灯"


def test_regulated_poem_validation_allows_selected_forms() -> None:
    assert _is_regulated_poem("巴山云作幕\n江风入夏城")
    assert _is_regulated_poem("巴山云作夏日幕\n江风轻入江城中\n晴光漫照山城路\n远客携风向东行")
    assert not _is_regulated_poem("雾从站台缓缓升起")
    assert not _is_regulated_poem("巴山云作幕\n江风入夏城\n远客向东行")
    assert not _is_regulated_poem("标题：巴山云作幕\n江风入夏城")
