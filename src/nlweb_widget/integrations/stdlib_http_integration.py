import asyncio
import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError


def make_stdlib_handler(widget: Any) -> type[BaseHTTPRequestHandler]:
    """Create a stdlib HTTP handler for the NLWeb protocol surfaces."""
    from ..models import MCPRequest, NLWebRequest
    from ..protocol import protocol_ask, protocol_ask_stream, protocol_discovery, protocol_health, protocol_mcp, streaming_requested

    class NLWebHandler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/.well-known/nlweb":
                self._json(200, protocol_discovery(widget))
                return
            if path == "/health":
                self._json(200, protocol_health(widget))
                return
            self._json(404, {"detail": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._json(400, {"detail": "Invalid JSON request"})
                return
            if self.path == "/ask":
                try:
                    request = NLWebRequest.model_validate(data)
                except ValidationError:
                    self._json(400, {"detail": "Invalid NLWeb request"})
                    return
                if streaming_requested(request):
                    loop = asyncio.new_event_loop()
                    iterator = protocol_ask_stream(widget, request).__aiter__()
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Transfer-Encoding", "chunked")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        while True:
                            try:
                                chunk = loop.run_until_complete(iterator.__anext__()).encode("utf-8")
                            except StopAsyncIteration:
                                break
                            self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                            self.wfile.write(chunk + b"\r\n")
                            self.wfile.flush()
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                    finally:
                        close = getattr(iterator, "aclose", None)
                        if close is not None:
                            loop.run_until_complete(close())
                        loop.close()
                    return
                payload = asyncio.run(protocol_ask(widget, request))
                self._json(200, payload)
                return
            if self.path == "/mcp":
                payload = asyncio.run(protocol_mcp(widget, data))
                self._json(200, payload)
                return
            self._json(404, {"detail": "not found"})

    return NLWebHandler
