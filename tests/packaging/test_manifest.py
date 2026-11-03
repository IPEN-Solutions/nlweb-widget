from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def test_widget_manifest_declares_lean_resource_boundary() -> None:
    data = tomllib.loads(
        Path("revision-iteration-manifest-0.9.11-r2.toml").read_text(encoding="utf-8")
    )
    packaging = data["packaging"]
    assert packaging["provider_runtime_must_remain_packaged"] is True
    assert packaging["example_infrastructure_must_not_be_packaged"] is True
    assert packaging["starter_profiles_must_not_be_packaged"] is True


def test_artifact_packaging_policy_is_fail_closed() -> None:
    data = tomllib.loads(
        Path("revision-iteration-manifest-0.9.11-r2.toml").read_text(encoding="utf-8")
    )
    policy = data["artifact_packaging"]
    assert policy["fail_closed"] is True
    for fragment in (".venv/", "__pycache__/", ".pytest_cache/", ".ruff_cache/"):
        assert fragment in policy["forbidden_path_fragments"]
    assert Path(".python-version").read_text(encoding="utf-8").strip() == "3.10"


def test_lifecycle_and_provider_hardening_is_declared() -> None:
    data = tomllib.loads(
        Path("revision-iteration-manifest-0.9.11-r2.toml").read_text(encoding="utf-8")
    )
    assert data["lifecycle"]["current"]["enabled_default"] is False


def test_test_tooling_hardening_is_declared() -> None:
    data = tomllib.loads(
        Path("revision-iteration-manifest-0.9.11-r2.toml").read_text(encoding="utf-8")
    )
    tooling = data["test_tooling"]
    assert tooling["anyio_test_constraint"] == ">=4.13,<4.14"
    assert tooling["ide_discovery_and_cli_suite_must_match"] is True


def test_test_dependency_graph_pins_compatible_anyio_line() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev = data["dependency-groups"]["dev"]
    assert "anyio>=4.13,<4.14" in dev
