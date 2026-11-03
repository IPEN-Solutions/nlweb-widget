from typing import Any

from ..models import MCPRequest, NLWebRequest
from ..protocol import protocol_ask, protocol_ask_stream, protocol_discovery, protocol_health, protocol_mcp, streaming_requested


_ASK_OPENAPI_SCHEMA = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "Natural-language query text."},
                "site": {"type": "string", "nullable": True},
            },
            "additionalProperties": True,
        },
        "context": {"type": "object", "nullable": True, "additionalProperties": True},
        "prefer": {"type": "object", "nullable": True, "additionalProperties": True},
        "meta": {"type": "object", "nullable": True, "additionalProperties": True},
    },
    "additionalProperties": True,
}

_ASK_OPENAPI_EXAMPLE = {
    "query": {"text": "What AI engineering services are available?", "site": "example"},
    "context": {},
    "prefer": {"mode": "list", "response_format": "conversational_search"},
    "meta": {"version": "0.55"},
}

_MCP_OPENAPI_SCHEMA = {
    "type": "object",
    "required": ["jsonrpc", "method"],
    "properties": {
        "jsonrpc": {"type": "string", "enum": ["2.0"]},
        "id": {"oneOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}]},
        "method": {"type": "string"},
        "params": {"type": "object", "nullable": True, "additionalProperties": True},
    },
    "additionalProperties": True,
}

_MCP_OPENAPI_EXAMPLE = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "ask",
        "arguments": {"query": {"text": "What services are available?"}},
    },
}


def mount_fastapi_nlweb(app: Any, widget: Any, prefix: str = "") -> Any:
    """Mount the NLWeb protocol surfaces on a FastAPI application."""
    from fastapi import APIRouter, Body
    from fastapi.responses import StreamingResponse
    from pydantic import ValidationError

    router = APIRouter()

    @router.post(
        "/ask",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": _ASK_OPENAPI_SCHEMA,
                        "examples": {"nlwebAsk": {"summary": "NLWeb ask", "value": _ASK_OPENAPI_EXAMPLE}},
                    }
                }
            }
        },
    )
    async def ask(payload: dict[str, Any] = Body(...)) -> Any:
        try:
            request_payload = NLWebRequest.model_validate(payload)
        except ValidationError as exc:
            # Preserve the widget's established HTTP contract: malformed /ask
            # payloads are HTTP 400 rather than FastAPI's default 422.
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Invalid NLWeb request") from exc
        if streaming_requested(request_payload):
            return StreamingResponse(
                protocol_ask_stream(widget, request_payload),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return await protocol_ask(widget, request_payload)

    @router.post(
        "/mcp",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": _MCP_OPENAPI_SCHEMA,
                        "examples": {"mcpAsk": {"summary": "MCP tools/call", "value": _MCP_OPENAPI_EXAMPLE}},
                    }
                }
            }
        },
    )
    async def mcp(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        # MCP invalid requests are protocol-level JSON-RPC errors and therefore
        # remain HTTP 200 responses from this binding.
        return await protocol_mcp(widget, payload)

    @router.get("/.well-known/nlweb")
    async def discovery() -> dict[str, object]:
        return protocol_discovery(widget)

    @router.get("/health")
    async def health() -> dict[str, str]:
        return protocol_health(widget)

    app.include_router(router, prefix=prefix)
    return app
