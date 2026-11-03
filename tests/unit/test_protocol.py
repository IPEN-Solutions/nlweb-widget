import pytest
from nlweb_widget.settings import NLWebSettings

from nlweb_widget import ContentDocument, NLWebRequest, NLWebWidget
from nlweb_widget.protocol import protocol_mcp


@pytest.mark.asyncio
async def test_ask_shape() -> None:
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    await widget.index(
        ContentDocument(
            id="1",
            url="https://example.test/p",
            title="Retail",
            content="AI retail services",
            schema_object={"@type": "Service"},
        )
    )
    response = await widget.ask(NLWebRequest(query={"text": "retail AI"}))
    assert response.results[0].name == "Retail"
    assert response.results[0].schema_object["@type"] == "Service"


@pytest.mark.asyncio
async def test_mcp_tools_call() -> None:
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    await widget.index(
        ContentDocument(
            id="1",
            url="https://example.test/p",
            title="Retail",
            content="AI retail services",
        )
    )
    response = await protocol_mcp(
        widget,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"query": {"text": "retail"}}},
        },
    )
    assert response["result"]["content"]
    assert response["result"]["structuredContent"]["_meta"]["response_type"] == "answer"
    assert response["result"]["isError"] is False
