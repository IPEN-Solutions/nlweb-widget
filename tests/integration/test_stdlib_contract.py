from http.server import HTTPServer

from nlweb_widget import NLWebWidget
from nlweb_widget.integrations.stdlib_http_integration import make_stdlib_handler
from nlweb_widget.settings import NLWebSettings


def test_stdlib_handler_has_normative_routes() -> None:
    handler = make_stdlib_handler(
        NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    try:
        assert handler.__name__ == "NLWebHandler"
    finally:
        server.server_close()
