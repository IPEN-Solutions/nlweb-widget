import asyncio
import hashlib
import urllib.request
from pathlib import Path

from .models import ContentSource


async def fingerprint_source(source: ContentSource, *, timeout: float = 15.0) -> str:
    value = await asyncio.wait_for(
        asyncio.to_thread(_read_source, source.location, timeout), timeout=timeout
    )
    return hashlib.sha256(value).hexdigest()


def _read_source(location: str, timeout: float) -> bytes:
    if location.startswith(("http://", "https://")):
        with urllib.request.urlopen(location, timeout=timeout) as response:
            return response.read()
    return Path(location).read_bytes()
