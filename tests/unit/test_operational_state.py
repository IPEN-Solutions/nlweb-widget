import pytest

from nlweb_widget import ContentDocument, NLWebRequest, NLWebWidget
from nlweb_widget.settings import NLWebSettings


@pytest.mark.asyncio
async def test_disabled_widget_does_not_project_or_retrieve() -> None:
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=False))
    await widget.index(
        ContentDocument(
            id="1",
            url="https://example.test/p",
            title="Retail",
            content="AI retail services",
        )
    )
    response = await widget.ask(NLWebRequest(query={"text": "retail"}))
    assert widget.effective_state == "disabled"
    assert response.results == []
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_enabled_widget_projects_and_retrieves() -> None:
    widget = NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))
    await widget.index(
        ContentDocument(
            id="1",
            url="https://example.test/p",
            title="Retail",
            content="AI retail services",
        )
    )
    response = await widget.ask(NLWebRequest(query={"text": "retail"}))
    assert widget.effective_state == "enabled"
    assert response.results


@pytest.mark.asyncio
async def test_startup_projects_configured_sources(tmp_path) -> None:
    import json

    data = tmp_path / "data.json"
    data.write_text(
        json.dumps(
            [
                {
                    "@id": "https://example.test/a",
                    "name": "Retail AI",
                    "description": "Retail services",
                }
            ]
        ),
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            {
                "sources": [
                    {"name": "domain", "kind": "schema_json", "location": "data.json"}
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = NLWebSettings(
        _env_file=None,
        enabled=True,
        content_sources_file=str(sources),
        content_sync_on_startup=True,
        content_sync_interval_seconds=0,
        content_sync_state_file=str(tmp_path / "state.json"),
    )
    widget = NLWebWidget(settings=settings)
    await widget.startup()
    response = await widget.ask(NLWebRequest(query={"text": "Retail"}))
    assert response.results[0].name == "Retail AI"
