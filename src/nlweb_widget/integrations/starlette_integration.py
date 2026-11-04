from collections.abc import Iterable
from typing import Any


def build_starlette_nlweb_routes(widget: Any) -> Iterable[Any]:
    """Build Starlette routes for the NLWeb protocol surfaces."""
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    from ..models import MCPRequest, NLWebRequest
    from ..protocol import (
        protocol_ask,
        protocol_ask_stream,
        protocol_discovery,
        protocol_health,
        protocol_mcp,
        streaming_requested,
    )

    async def ask(request: Any) -> JSONResponse:
        payload = NLWebRequest.model_validate(await request.json())
        if streaming_requested(payload):
            return StreamingResponse(
                protocol_ask_stream(widget, payload),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return JSONResponse(await protocol_ask(widget, payload))

    async def mcp(request: Any) -> JSONResponse:
        payload = MCPRequest.model_validate(await request.json())
        return JSONResponse(await protocol_mcp(widget, payload))

    async def discovery(request: Any) -> JSONResponse:
        return JSONResponse(protocol_discovery(widget))

    async def health(request: Any) -> JSONResponse:
        return JSONResponse(protocol_health(widget))

    return [
        Route("/ask", ask, methods=["POST"]),
        Route("/mcp", mcp, methods=["POST"]),
        Route("/.well-known/nlweb", discovery),
        Route("/health", health),
    ]
