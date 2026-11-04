import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from .models import MCPRequest, NLWebRequest
from .widget import NLWebWidget


def protocol_discovery(widget: NLWebWidget) -> dict[str, object]:
    return widget.discovery()


def protocol_health(widget: NLWebWidget | None = None) -> dict[str, str]:
    state = widget.effective_state if widget is not None else "enabled"
    return {
        "status": "ok" if state == "enabled" else "disabled",
        "service": "nlweb-widget",
    }


async def protocol_ask(widget: NLWebWidget, payload: NLWebRequest) -> dict[str, Any]:
    """Execute the normative NLWeb ``ask`` operation."""
    return (await widget.ask(payload)).model_dump(by_alias=True, exclude_none=True)


def _mcp_error(request_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _ask_tool() -> dict[str, Any]:
    return {
        "name": "ask",
        "description": "Natural Language interface to this NLWeb site.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "object",
                    "description": "The query object containing text and optional domain filters.",
                    "properties": {
                        "text": {"type": "string"},
                        "site": {"type": "string"},
                    },
                    "required": ["text"],
                    "additionalProperties": True,
                },
                "context": {"type": "object"},
                "prefer": {"type": "object"},
                "meta": {"type": "object"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def _await_tool() -> dict[str, Any]:
    return {
        "name": "await",
        "description": "Check status or cancel a long-running NLWeb promise.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "promise_token": {"type": "string"},
                "action": {"type": "string", "enum": ["checkin", "cancel"]},
                "meta": {"type": "object"},
            },
            "required": ["promise_token", "action"],
        },
    }


async def protocol_mcp(
    widget: NLWebWidget, request: MCPRequest | dict[str, Any]
) -> dict[str, Any]:
    """MCP binding for NLWeb v0.55.

    Tool discovery is independent from execution. Application-level NLWeb
    failures are returned inside a successful MCP tool result with
    ``isError=true``; unknown tools and unsupported JSON-RPC methods are MCP
    protocol errors as required by the MCP tool contract.
    """
    try:
        request = MCPRequest.model_validate(request)
    except ValidationError:
        return _mcp_error(None, -32600, "Invalid Request")
    params = request.params or {}

    if request.method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {"tools": [_ask_tool()]},
        }

    if request.method == "tools/call":
        name = params.get("name")
        if name not in {"ask"}:
            return _mcp_error(request.id, -32602, f"Unknown tool: {name}")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _mcp_error(request.id, -32602, "Tool arguments must be an object")
        try:
            result = await widget.ask(NLWebRequest.model_validate(arguments))
        except ValidationError as exc:
            return _mcp_error(request.id, -32602, f"Invalid ask arguments: {exc}")
        payload = result.model_dump(by_alias=True, exclude_none=True)
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result.model_dump_json(
                            by_alias=True, exclude_none=True
                        ),
                    }
                ],
                "structuredContent": payload,
                "_meta": result.meta,
                "isError": result.meta.get("response_type") == "failure",
            },
        }

    return _mcp_error(request.id, -32601, "Method not found")


def streaming_requested(payload: NLWebRequest) -> bool:
    """Interpret the protocol streaming preference without treating "false" as true."""
    value = (payload.prefer or {}).get("streaming", False)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


async def protocol_ask_stream(
    widget: NLWebWidget, payload: NLWebRequest
) -> AsyncIterator[str]:
    """Yield NLWeb v0.55 Server-Sent Events for an ``/ask`` request.

    The event contract follows the official specification: one ``start`` event,
    zero or more indexed ``result`` events, an optional ``error`` event for an
    application-level failure, and one ``complete`` event.
    """
    # The start event must be yielded before widget.ask() is awaited. Otherwise
    # an HTTP server cannot flush the SSE response until the full query finishes,
    # making the streaming preference appear ineffective to clients.
    request_meta = dict(payload.meta or {})
    version = str(request_meta.get("version") or "0.55")
    start_meta: dict[str, Any] = {
        "version": version,
        "streaming": True,
    }
    yield _sse_event("start", {"_meta": start_meta})

    prefer = dict(payload.prefer or {})
    prefer["streaming"] = False
    request = payload.model_copy(update={"prefer": prefer})
    response = await widget.ask(request)
    response_payload = response.model_dump(by_alias=True, exclude_none=True)
    response_meta = dict(response_payload.get("_meta") or {})
    version = str(response_meta.get("version") or version)
    response_type = str(response_meta.get("response_type") or "answer")

    if response_type == "failure":
        failure_payload: dict[str, Any] = {"_meta": start_meta}
        if response_payload.get("error") is not None:
            failure_payload["error"] = response_payload["error"]
        yield _sse_event("error", failure_payload)
    else:
        for index, item in enumerate(response_payload.get("results", [])):
            yield _sse_event("result", {"index": index, "item": item})

    complete_meta: dict[str, Any] = {"version": version}
    session_context = response_meta.get("session_context")
    if isinstance(session_context, dict):
        complete_meta["session_context"] = session_context
    yield _sse_event("complete", {"_meta": complete_meta})


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"
