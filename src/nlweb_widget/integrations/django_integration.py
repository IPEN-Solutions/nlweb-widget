from typing import Any


def build_django_nlweb_urls(widget: Any) -> list[Any]:
    """Build Django URL patterns for the NLWeb protocol surfaces."""
    import json

    from django.http import JsonResponse, StreamingHttpResponse
    from django.urls import path

    from ..models import MCPRequest, NLWebRequest
    from ..protocol import protocol_ask, protocol_ask_stream, protocol_discovery, protocol_health, protocol_mcp, streaming_requested

    async def ask(request: Any) -> Any:
        payload = NLWebRequest.model_validate(json.loads(request.body or b"{}"))
        if streaming_requested(payload):
            return StreamingHttpResponse(
                protocol_ask_stream(widget, payload),
                content_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return JsonResponse(await protocol_ask(widget, payload))

    async def mcp(request: Any) -> JsonResponse:
        payload = MCPRequest.model_validate(json.loads(request.body or b"{}"))
        return JsonResponse(await protocol_mcp(widget, payload))

    def discovery(request: Any) -> JsonResponse:
        return JsonResponse(protocol_discovery(widget))

    def health(request: Any) -> JsonResponse:
        return JsonResponse(protocol_health(widget))

    return [
        path("ask", ask),
        path("mcp", mcp),
        path(".well-known/nlweb", discovery),
        path("health", health),
    ]
