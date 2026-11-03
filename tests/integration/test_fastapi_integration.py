from fastapi import FastAPI
from fastapi.testclient import TestClient
from nlweb_widget.settings import NLWebSettings

from nlweb_widget import ContentDocument, NLWebWidget
from nlweb_widget.integrations.fastapi_integration import mount_fastapi_nlweb


def test_fastapi_normative_surface() -> None:
    import asyncio

    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    asyncio.run(
        widget.index(
            ContentDocument(
                id="1",
                url="https://example.test/p",
                title="Retail",
                content="AI retail services",
            )
        )
    )
    app = mount_fastapi_nlweb(FastAPI(), widget)
    with TestClient(app) as client:
        assert client.post("/ask", json={"query": {"text": "retail"}}).status_code == 200
        mcp_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert mcp_response.json()["result"]["tools"]
        assert client.get("/.well-known/nlweb").json()["endpoints"]["ask"] == "/ask"
        assert client.get("/health").json()["status"] == "ok"


def test_fastapi_streaming_uses_normative_sse_events() -> None:
    import asyncio

    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    asyncio.run(widget.index(ContentDocument(
        id="stream-1", url="https://example.test/stream", title="Streaming service",
        content="Streaming protocol example", schema_object={"@type": "Service"},
    )))
    app = mount_fastapi_nlweb(FastAPI(), widget)
    with TestClient(app) as client:
        response = client.post("/ask", json={
            "query": {"text": "streaming protocol"},
            "prefer": {"streaming": True},
            "meta": {"version": "0.55", "session_context": {"conversation_id": "qa-1"}},
        })
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: start\n" in body
    assert '"streaming":true' in body
    assert "event: result\n" in body
    assert '"index":0' in body
    assert "event: complete\n" in body
    assert '"conversation_id":"qa-1"' in body


def test_streaming_string_false_returns_json() -> None:
    import asyncio

    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    asyncio.run(widget.index(ContentDocument(
        id="stream-false", url="https://example.test/stream-false", title="False streaming",
        content="String false preference",
    )))
    app = mount_fastapi_nlweb(FastAPI(), widget)
    with TestClient(app) as client:
        response = client.post("/ask", json={
            "query": {"text": "string false preference"},
            "prefer": {"streaming": "false"},
        })
    assert response.headers["content-type"].startswith("application/json")


def test_fastapi_streaming_accepts_string_true() -> None:
    import asyncio

    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    asyncio.run(widget.index(ContentDocument(
        id="stream-string-true", url="https://example.test/stream-string-true",
        title="String true streaming", content="Streaming preference as a string",
    )))
    app = mount_fastapi_nlweb(FastAPI(), widget)
    with TestClient(app) as client:
        response = client.post("/ask", json={
            "query": {"text": "Streaming preference as a string"},
            "prefer": {"streaming": "true"},
        })
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith("event: start\n")
    assert "event: result\n" in response.text
    assert "event: complete\n" in response.text
