import inspect
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable, Iterable
from html.parser import HTMLParser
from typing import Any, Protocol

from ..errors import ContentIngestionError, OptionalDependencyError
from ..models import ContentDocument
from .models import ContentSource, ContentSourceKind


class ContentAdapter(Protocol):
    async def read(self, source: ContentSource) -> list[ContentDocument]: ...


class SchemaJSONAdapter:
    async def read(self, source: ContentSource) -> list[ContentDocument]:
        raw = await _read_location(source.location)
        payload = json.loads(raw)
        objects = _objects(payload)
        return [_schema_document(item, source, index) for index, item in enumerate(objects)]


class RSSAtomAdapter:
    async def read(self, source: ContentSource) -> list[ContentDocument]:
        root = ET.fromstring(await _read_location(source.location))
        is_atom = root.tag.lower().endswith("feed")
        entries = root.findall(".//{*}entry") if is_atom else root.findall(".//item")
        documents: list[ContentDocument] = []
        for index, entry in enumerate(entries):
            title = _xml_text(entry, "title") or f"entry-{index}"
            url = _xml_text(entry, "link")
            link = entry.find("{*}link")
            if link is not None:
                url = url or link.attrib.get("href", "")
            url = url or f"{source.location}#{index}"
            text = _xml_text(entry, "description", "summary", "content")
            documents.append(
                ContentDocument(
                    id=url,
                    url=url,
                    title=title,
                    content=f"{title}\n{text}".strip(),
                    site=source.site,
                    metadata={"source": source.name},
                )
            )
        return documents


class SitemapAdapter:
    async def read(self, source: ContentSource) -> list[ContentDocument]:
        root = ET.fromstring(await _read_location(source.location))
        return [
            ContentDocument(
                id=url,
                url=url,
                title=url,
                content=url,
                site=source.site,
                metadata={"source": source.name},
            )
            for node in root.findall(".//{*}loc")
            if (url := (node.text or "").strip())
        ]


class WebPageSchemaAdapter:
    async def read(self, source: ContentSource) -> list[ContentDocument]:
        parser = _SchemaParser()
        parser.feed(await _read_location(source.location))
        parser.close()
        return [document.model_copy(update={"site": source.site}) for document in parser.documents]


class CallableAdapter:
    def __init__(self, provider: Callable[[ContentSource], Any]) -> None:
        self._provider = provider

    async def read(self, source: ContentSource) -> list[ContentDocument]:
        result = self._provider(source)
        result = await result if inspect.isawaitable(result) else result
        return [_coerce_document(item, source) for item in result]


class DocumentAdapter:
    """Optional Docling-backed adapter for common unstructured documents."""

    async def read(self, source: ContentSource) -> list[ContentDocument]:
        import asyncio
        from pathlib import Path

        try:
            import docling.document_converter  # noqa: F401
        except ImportError as exc:
            raise OptionalDependencyError(
                "Document ingestion requires the 'documents' extra (Docling)"
            ) from exc

        def convert() -> ContentDocument:
            # Keep the optional Docling path deterministic on CPU-only hosts.
            # PDF layout/table/OCR inference can otherwise invoke Torch/RT-DETR
            # even when DOCLING_DEVICE=cpu; the backend text path is sufficient
            # for authoritative text projection and remains overrideable.
            converter = _build_docling_converter()
            result = converter.convert(source.location)
            document = result.document
            markdown = document.export_to_markdown()
            title = Path(source.location).stem or source.name
            return ContentDocument(
                id=f"{source.name}:{source.location}",
                url=source.location,
                title=title,
                content=markdown,
                site=source.site,
                metadata={"source": source.name, "parser": "docling"},
            )

        return [await asyncio.to_thread(convert)]


def _build_docling_converter() -> Any:
    """Build a Docling converter with environment-driven, CPU-safe PDF options."""
    import os

    from docling.document_converter import DocumentConverter

    device = os.getenv("DOCLING_DEVICE", "auto")
    threads = max(1, int(os.getenv("DOCLING_NUM_THREADS", os.getenv("OMP_NUM_THREADS", "4"))))
    safe_pdf = os.getenv("DOCLING_SAFE_PDF", "false").strip().lower() in {"1", "true", "yes", "on"}

    if not safe_pdf:
        return DocumentConverter()

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import AcceleratorOptions, PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    pdf_options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(device=device, num_threads=threads),
        do_ocr=False,
        do_table_structure=False,
        force_backend_text=True,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }
    )


class DatabaseAdapter:
    def __init__(
        self,
        provider: Callable[[ContentSource], Awaitable[Iterable[dict[str, Any]]]],
    ) -> None:
        self._provider = provider

    async def read(self, source: ContentSource) -> list[ContentDocument]:
        return [_coerce_document(item, source) for item in await self._provider(source)]


def _objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)]
        return [payload]
    return []


def _schema_document(item: dict[str, Any], source: ContentSource, index: int) -> ContentDocument:
    nested_schema = item.get("schema_object")
    schema = nested_schema if isinstance(nested_schema, dict) else item
    url = str(
        item.get("url")
        or schema.get("url")
        or item.get("@id")
        or schema.get("@id")
        or f"{source.location}#{index}"
    )
    title = str(
        item.get("name")
        or item.get("title")
        or schema.get("name")
        or schema.get("headline")
        or url
    )
    content = str(item.get("content") or item.get("description") or _flatten_schema(schema))
    return ContentDocument(
        id=str(item.get("id") or url),
        url=url,
        title=title,
        content=content,
        schema_object=schema,
        site=source.site,
        metadata={"source": source.name},
    )


def _coerce_document(item: Any, source: ContentSource) -> ContentDocument:
    if isinstance(item, ContentDocument):
        return item.model_copy(update={"site": item.site or source.site})
    if not isinstance(item, dict):
        raise TypeError("Content adapters must return mappings or ContentDocument")
    identifier = str(item.get("id") or item.get("url") or f"{source.name}:{hash(str(item))}")
    title = str(item.get("title") or item.get("name") or identifier)
    content = str(item.get("content") or item.get("text") or item.get("description") or title)
    schema_object = item.get("schema_object")
    return ContentDocument(
        id=identifier,
        url=str(item.get("url") or identifier),
        title=title,
        content=content,
        schema_object=schema_object if isinstance(schema_object, dict) else {},
        site=str(item.get("site") or source.site),
        metadata={
            key: value
            for key, value in item.items()
            if key not in {
                "id", "url", "title", "name", "content", "text",
                "description", "schema_object", "site",
            }
        },
    )


def _flatten_schema(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(
            f"{key}: {_flatten_schema(item)}"
            for key, item in value.items()
            if key != "@context"
        )
    if isinstance(value, list):
        return " ".join(_flatten_schema(item) for item in value)
    return str(value)


def _xml_text(element: ET.Element, *names: str) -> str:
    for name in names:
        node = element.find(name) or element.find(f"{{*}}{name}")
        if node is not None and node.text:
            return node.text.strip()
    return ""


async def _read_location(location: str) -> str:
    import asyncio

    if re.match(r"^https?://", location, re.IGNORECASE):
        return await asyncio.to_thread(_read_url, location)
    return await asyncio.to_thread(_read_file, location)


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def _read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


class _SchemaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.documents: list[ContentDocument] = []
        self._jsonld: list[str] = []
        self._in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = dict(attrs)
        self._in_jsonld = attributes.get("type", "").lower() == "application/ld+json"

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._jsonld.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_jsonld = False

    def close(self) -> None:
        super().close()
        for raw in self._jsonld:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for index, item in enumerate(_objects(payload)):
                if item.get("url") or item.get("@id"):
                    source = ContentSource(
                        name="webpage", kind="webpage_schema", location="webpage"
                    )
                    self.documents.append(_schema_document(item, source, index))
