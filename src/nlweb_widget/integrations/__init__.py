from .django_integration import build_django_nlweb_urls
from .fastapi_integration import mount_fastapi_nlweb
from .flask_integration import mount_flask_nlweb
from .starlette_integration import build_starlette_nlweb_routes
from .stdlib_http_integration import make_stdlib_handler

__all__ = [
    "build_django_nlweb_urls",
    "build_starlette_nlweb_routes",
    "make_stdlib_handler",
    "mount_fastapi_nlweb",
    "mount_flask_nlweb",
]
