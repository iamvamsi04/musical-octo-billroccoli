from uuid import uuid4
import httpx
from streamlit.testing.v1 import AppTest
from config import settings


def test_streamlit_chat_flow(monkeypatch):
    cid = str(uuid4())
    def respond(self, method, url, **kwargs):
        if url.endswith("/health"):
            data = {"model_configured": True, "model": "test-model"}
        elif url.endswith("/conversations"):
            data = {"conversation_id": cid}
        elif url.endswith("/chat"):
            assert kwargs["json"]["conversation_id"] == cid
            data = {"response": "There are 4 customers.", "invoices": []}
        else:
            raise AssertionError(url)
        return httpx.Response(200, json=data, request=httpx.Request(method, url))
    monkeypatch.setattr(httpx.Client, "request", respond)
    app = AppTest.from_file(str(settings.ROOT / "ui/streamlit_app.py"), default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "💳 Billing Agent"
    app.chat_input[0].set_value("How many customers?").run()
    assert not app.exception
    assert any(m.value == "There are 4 customers." for m in app.markdown)
