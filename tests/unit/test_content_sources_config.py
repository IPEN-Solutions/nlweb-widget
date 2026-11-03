import json

from nlweb_widget.content.service import load_content_sources


def test_load_content_sources_from_list(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [{"name": "domain", "kind": "schema_json", "location": "data.json"}]
        ),
        encoding="utf-8",
    )
    sources = load_content_sources(path)
    assert sources[0].name == "domain"
    assert sources[0].kind.value == "schema_json"


def test_load_content_sources_from_object(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {"sources": [{"name": "domain", "kind": "schema_json", "location": "data.json"}]}
        ),
        encoding="utf-8",
    )
    assert len(load_content_sources(path)) == 1
