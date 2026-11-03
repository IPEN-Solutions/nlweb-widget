# AGENTS.md

## Project
`nlweb-widget` is a framework-neutral Python library that exposes an authoritative domain-data projection through the NLWeb protocol. The published runtime is intentionally lean; optional providers, framework adapters, and reference examples remain separated.

## Authoritative references
- Read the active `revision-iteration-manifest-*.toml` and `.nlweb-build-manifest.toml` before mutation work.
- Treat `ARCHITECTURE.md`, `MUTATION.md`, `docs-provider-evaluations.md`, tests, and public docs as repository evidence; do not invent missing contracts.
- Preserve the forward-only baseline and hash-addressed rollback policy.

## Change boundaries
- Do not modify an immutable baseline or historical candidate.
- Do not introduce example-only dependencies into the runtime package.
- Do not break public APIs/import paths/endpoints/configuration/provider contracts.
- Protocol changes are limited to conformance corrections, normative failure semantics, or additive optional capabilities.
- Keep framework integrations thin and keep authoritative application data separate from AI-facing retrieval projections.
- Avoid opportunistic refactors, renames, dependency upgrades, or unrelated cleanup.

## Commands
- Install: `uv sync --dev`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Build: `uv build`
- Optional full dependency QA: `uv sync --dev --all-extras`

## Verification
Run the smallest relevant checks first, then the full declared gates for release work. Configured optional-provider tests must exercise the real configured backend; unconfigured providers are skipped. A configured-but-unavailable provider is a failure.

## Security
Never commit credentials, tokens, private keys, `.env`, or `.env.agentic.coding`. Use `.env.agentic.coding.example` only as a classification/template file. Never place production secrets in examples, tests, CI logs, or generated bundles.

## Agent workflow
For non-trivial work: inspect → plan → smallest coherent edit → synchronize manifests/docs/tests → validate → report hashes and remaining risks. Human approval remains required for release promotion, rollback, credential use, and changes to protected agent/governance files.
