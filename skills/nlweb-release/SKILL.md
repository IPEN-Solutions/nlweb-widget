---
name: nlweb-release
description: Build, validate, hash, and promote nlweb-widget releases while preserving forward-only manifests, immutable baselines, compatibility gates, trusted publishing, and explicit rollback rules. Use for release candidates, version tags, PyPI publication, or release-bundle generation.
---

# Release workflow

1. Read the active revision manifest and `.nlweb-build-manifest.toml`.
2. Confirm the requested version/tag matches `pyproject.toml`.
3. Confirm compatibility gates remain non-breaking unless an explicit approved mutation says otherwise.
4. Run dependency resolution, tests, lint, format, and `uv build`.
5. Validate documentation and artifact-integrity metadata when the release scope includes them.
6. Generate deterministic SHA-256 evidence for the final files and archive.
7. Never overwrite an immutable baseline. A failed candidate does not advance the baseline.
8. Release publication uses GitHub Actions trusted publishing and provenance; credentials must not be embedded in the repository.
9. Rollback is explicit and must name a hash-addressed target baseline.

See `references/release-gates.md` for the detailed gate checklist.
