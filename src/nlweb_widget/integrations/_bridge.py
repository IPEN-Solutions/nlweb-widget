import asyncio
from collections.abc import Awaitable
from typing import TypeVar


T = TypeVar("T")


def run_async(awaitable: Awaitable[T]) -> T:
    """Run an awaitable from synchronous framework adapter code."""
    return asyncio.run(awaitable)
