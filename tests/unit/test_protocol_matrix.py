import pytest
from pydantic import ValidationError

from nlweb_widget import ContentDocument, NLWebRequest, NLWebWidget
from nlweb_widget.protocol import protocol_mcp
from nlweb_widget.settings import NLWebSettings


@pytest.fixture
def widget() -> NLWebWidget:
    return NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))


@pytest.mark.asyncio
async def test_ask_request_matrix_accepts_context_meta_preferences_and_filters(
    widget: NLWebWidget,
) -> None:
    await widget.index(
        ContentDocument(
            id="service-1",
            url="https://example.test/ai",
            title="AI Service",
            content="AI transformation service",
            site="example.test",
            schema_object={"@type": "Service", "areaServed": "Canada"},
        )
    )
    request = NLWebRequest(
        query={"text": "AI service", "site": "example.test", "areaServed": "Canada"},
        context={"@type": "ConversationalContext", "text": "business services"},
        prefer={
            "streaming": True,
            "response_format": "conversational_search",
            "mode": "list, summarize",
            "accept-language": "en",
            "user-agent": "qa-client/1",
        },
        meta={
            "version": "0.55",
            "session_context": {"conversation_id": "c1"},
            "user": "qa-user",
            "remember": True,
        },
    )
    response = await widget.ask(request)
    assert response.meta["response_type"] == "answer"
    assert response.meta["version"] == "0.55"
    assert response.meta["response_format"] == "conversational_search"
    assert response.meta["streaming"] is False
    assert response.meta["session_context"] == {"conversation_id": "c1"}
    assert response.results[0].schema_type == "SearchSummary"
    assert response.results[0].text
    assert response.results[1].schema_type == "Service"


@pytest.mark.asyncio
async def test_chatgpt_app_response_format_is_additive(widget: NLWebWidget) -> None:
    await widget.index(
        ContentDocument(
            id="1",
            url="https://example.test/1",
            title="One",
            content="one service",
            schema_object={"@type": "Service", "name": "One"},
        )
    )
    response = await widget.ask(
        NLWebRequest(
            query={"text": "one"},
            prefer={"response_format": "chatgpt_app"},
        )
    )
    assert response.meta["response_format"] == "chatgpt_app"
    assert response.content == [{"type": "text", "text": "one service"}]
    assert response.structured_data[0]["@type"] == "Service"


@pytest.mark.asyncio
async def test_invalid_protocol_version_is_explicit_failure(
    widget: NLWebWidget,
) -> None:
    response = await widget.ask(
        NLWebRequest(query={"text": "anything"}, meta={"version": "0.54"})
    )
    assert response.meta["response_type"] == "failure"
    assert response.error.code == "INVALID_QUERY"


@pytest.mark.asyncio
async def test_mcp_tools_list_is_independent_and_normative(widget: NLWebWidget) -> None:
    response = await protocol_mcp(
        widget,
        {"jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {}},
    )
    assert response["result"]["tools"][0]["name"] == "ask"
    schema = response["result"]["tools"][0]["inputSchema"]
    assert set(schema["required"]) == {"query"}
    assert "context" in schema["properties"]
    assert "prefer" in schema["properties"]
    assert "meta" in schema["properties"]


@pytest.mark.asyncio
async def test_mcp_application_failure_is_tool_error_not_jsonrpc_error(
    widget: NLWebWidget,
) -> None:
    response = await protocol_mcp(
        widget,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"query": {"text": "missing"}}},
        },
    )
    assert "error" not in response
    assert response["result"]["isError"] is True
    assert (
        response["result"]["structuredContent"]["_meta"]["response_type"] == "failure"
    )


@pytest.mark.asyncio
async def test_mcp_unknown_tool_and_method_use_jsonrpc_errors(
    widget: NLWebWidget,
) -> None:
    unknown_tool = await protocol_mcp(
        widget,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "not-a-tool", "arguments": {}},
        },
    )
    assert unknown_tool["error"]["code"] == -32602

    unknown_method = await protocol_mcp(
        widget,
        {"jsonrpc": "2.0", "id": 4, "method": "not-a-method", "params": {}},
    )
    assert unknown_method["error"]["code"] == -32601


def test_malformed_mcp_request_is_rejected_by_model() -> None:
    with pytest.raises(ValidationError):
        NLWebRequest.model_validate({"context": {}})
