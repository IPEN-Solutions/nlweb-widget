import json

import pytest

from nlweb_widget.content import ContentSource, ContentSourceKind, ContentSyncService
from nlweb_widget.content.adapters import SchemaJSONAdapter
from nlweb_widget.content.state import StateStore


@pytest.mark.asyncio
async def test_schema_json_projects_structured_domain_data(tmp_path):
    source_file = tmp_path / "data.json"
    source_file.write_text(
        json.dumps(
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "ProfessionalService",
                        "@id": "https://example.test/#agency",
                        "url": "https://example.test/",
                        "name": "AI Transformation Agency",
                        "description": "AI transformation services for retailers.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = ContentSource(
        name="domain-json",
        kind=ContentSourceKind.SCHEMA_JSON,
        location=str(source_file),
        site="retail",
    )
    documents = await SchemaJSONAdapter().read(source)
    assert documents[0].schema_object["@type"] == "ProfessionalService"
    assert documents[0].site == "retail"
    assert "retailers" in documents[0].content


@pytest.mark.asyncio
async def test_sync_without_target_preserves_projection_for_consumer(tmp_path):
    source_file = tmp_path / "data.json"
    source_file.write_text(
        json.dumps({"@id": "https://example.test/service", "name": "Retail AI"}),
        encoding="utf-8",
    )
    service = ContentSyncService(state_store=StateStore(tmp_path / "state.json"))
    result = await service.sync(
        ContentSource(
            name="domain",
            kind=ContentSourceKind.SCHEMA_JSON,
            location=str(source_file),
        )
    )
    assert result.status == "ok"
    assert result.total_loaded == 1


@pytest.mark.asyncio
async def test_state_store_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    from nlweb_widget.content.models import SourceState

    await store.put(SourceState(source="demo", fingerprint="abc", last_status="ok"))
    state = await store.get("demo")
    assert state is not None
    assert state.fingerprint == "abc"
