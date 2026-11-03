import sys
import types
from pathlib import Path

import pytest

from nlweb_widget.content.adapters import DocumentAdapter
from nlweb_widget.content.models import ContentSource, ContentSourceKind


@pytest.mark.asyncio
async def test_custom_source_uses_docling_adapter(monkeypatch, tmp_path: Path) -> None:
    class FakeDocument:
        def export_to_markdown(self):
            return "# Converted\n\nPortable content"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, location):
            assert location.endswith("sample.pdf")
            return FakeResult()

    module = types.SimpleNamespace(DocumentConverter=FakeConverter)
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)
    monkeypatch.setitem(sys.modules, "docling", types.SimpleNamespace())
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"placeholder")

    source = ContentSource(
        name="sample",
        kind=ContentSourceKind.CUSTOM,
        location=str(sample),
    )
    documents = await DocumentAdapter().read(source)
    assert documents[0].content.startswith("# Converted")
    assert documents[0].metadata["parser"] == "docling"
