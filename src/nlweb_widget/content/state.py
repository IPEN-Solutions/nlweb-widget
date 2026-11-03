import asyncio
import json
from pathlib import Path

from .models import SourceState


class StateStore:
    """Small JSON state store for source fingerprints and sync outcomes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def get(self, source: str) -> SourceState | None:
        data = await asyncio.to_thread(self._read)
        value = data.get(source)
        return SourceState.model_validate(value) if value else None

    async def put(self, state: SourceState) -> None:
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            data[state.source] = state.model_dump(mode="json")
            await asyncio.to_thread(self._write, data)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
