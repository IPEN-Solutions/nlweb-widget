from fastapi import FastAPI
from fastapi.testclient import TestClient

from nlweb_widget import NLWebWidget
from nlweb_widget.integrations.fastapi_integration import mount_fastapi_nlweb
from nlweb_widget.settings import NLWebSettings


def test_fastapi_malformed_ask_uses_400() -> None:
    app = FastAPI()
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    mount_fastapi_nlweb(app, widget)
    response = TestClient(app).post("/ask", json={"context": {}})
    assert response.status_code == 400


def test_mcp_invalid_jsonrpc_request_is_jsonrpc_error() -> None:
    app = FastAPI()
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    mount_fastapi_nlweb(app, widget)
    response = TestClient(app).post("/mcp", json={"method": "tools/list"})
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32600
