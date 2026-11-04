from typing import Any


def mount_flask_nlweb(app: Any, widget: Any, prefix: str = "") -> Any:
    """Mount the NLWeb protocol surfaces on a Flask application."""
    import asyncio

    from flask import Blueprint, Response, jsonify, request

    from ..models import MCPRequest, NLWebRequest
    from ..protocol import (
        protocol_ask,
        protocol_ask_stream,
        protocol_discovery,
        protocol_health,
        protocol_mcp,
        streaming_requested,
    )

    blueprint = Blueprint("nlweb_widget", __name__)

    @blueprint.post("/ask")
    def ask() -> Any:
        payload = NLWebRequest.model_validate(request.get_json())
        if not streaming_requested(payload):
            return jsonify(asyncio.run(protocol_ask(widget, payload)))

        def events() -> Any:
            loop = asyncio.new_event_loop()
            iterator = protocol_ask_stream(widget, payload).__aiter__()
            try:
                while True:
                    try:
                        yield loop.run_until_complete(iterator.__anext__())
                    except StopAsyncIteration:
                        break
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    loop.run_until_complete(close())
                loop.close()

        return Response(
            events(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @blueprint.post("/mcp")
    async def mcp() -> Any:
        return jsonify(
            await protocol_mcp(widget, MCPRequest.model_validate(request.get_json()))
        )

    @blueprint.get("/.well-known/nlweb")
    def discovery() -> Any:
        return jsonify(protocol_discovery(widget))

    @blueprint.get("/health")
    def health() -> Any:
        return jsonify(protocol_health(widget))

    app.register_blueprint(blueprint, url_prefix=prefix)
    return app
