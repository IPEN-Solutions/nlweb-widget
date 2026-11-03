# Release gates

- `uv sync --dev` succeeds in a clean environment.
- `uv run pytest` passes; conditional optional providers are skipped only when unconfigured.
- `uv run ruff check .` passes.
- `uv run ruff format --check .` passes.
- `uv build` produces the expected distribution artifacts.
- The project version equals the release tag without a leading `v`.
- Revision/build manifests are internally consistent and hash-addressed.
- Generated archives contain no credentials, virtual environments, caches, compiled bytecode, or build output.
- The final archive SHA-256 and tree hash are recorded before promotion.
