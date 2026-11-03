from pathlib import Path


def test_production_package_has_no_example_resource_trees() -> None:
    root = Path(__file__).parents[2]
    assert not (root / "src" / "nlweb_widget" / "resources").exists()
    assert not (root / "infra").exists()


def test_runtime_provider_implementations_remain_present() -> None:
    root = Path(__file__).parents[2]
    assert (root / "src" / "nlweb_widget" / "content" / "store.py").is_file()
    assert (root / "src" / "nlweb_widget" / "content" / "neo4j.py").is_file()
