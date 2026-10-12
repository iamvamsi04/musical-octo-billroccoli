from uuid import uuid4
from fastapi.testclient import TestClient
from api.main import app
from config import settings


class Engine:
    def __init__(self):
        self.calls = 0
        self.histories = []
    async def chat(self, message, history, customer_id):
        self.calls += 1
        self.histories.append(history)
        return {"response": f"Hello {customer_id}", "invoices": []}


def test_api_manages_engine_lifecycle():
    events = []
    class ManagedEngine(Engine):
        async def start(self):
            events.append("start")
        async def close(self):
            events.append("close")
    app.state.engine = ManagedEngine()
    with TestClient(app):
        assert events == ["start"]
    assert events == ["start", "close"]


def test_chat_history_and_idempotency():
    engine = Engine()
    app.state.engine = engine
    with TestClient(app) as client:
        cid = client.post("/conversations", json={"customer_id": "CUST001"}).json()["conversation_id"]
        body = {"conversation_id": cid, "request_id": str(uuid4()), "message": "Hi"}
        first = client.post("/chat", json=body)
        assert first.status_code == 200
        assert client.post("/chat", json=body).json() == first.json()
        assert engine.calls == 1
        assert client.post("/chat", json={**body, "message": "Different"}).status_code == 409
        client.post("/chat", json={**body, "request_id": str(uuid4()), "message": "Follow up"})
        assert len(engine.histories[1]) == 2
        assert len(client.get(f"/conversations/{cid}").json()["messages"]) == 4
        assert client.post("/chat", json={**body, "conversation_id": str(uuid4())}).status_code == 404


def test_api_key(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-secret")
    app.state.engine = Engine()
    with TestClient(app) as client:
        assert client.post("/conversations", json={}).status_code == 401
        assert client.post("/conversations", json={}, headers={"X-API-Key": "test-secret"}).status_code == 200


def test_failed_turn_cannot_replay():
    class Failing:
        async def chat(self, *args):
            raise RuntimeError("unavailable")
    app.state.engine = Failing()
    with TestClient(app) as client:
        cid = client.post("/conversations", json={}).json()["conversation_id"]
        body = {"conversation_id": cid, "request_id": str(uuid4()), "message": "Place order"}
        assert client.post("/chat", json=body).status_code == 503
        assert client.post("/chat", json=body).status_code == 409
