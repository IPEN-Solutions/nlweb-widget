import asyncio
from collections.abc import Awaitable, Callable


class ContentSyncScheduler:
    """Optional background scheduler for a content synchronization callback."""

    def __init__(self, callback: Callable[[], Awaitable[object]], interval_seconds: float) -> None:
        self._callback = callback
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._callback()
