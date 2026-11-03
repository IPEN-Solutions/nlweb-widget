# Agent Skills

This repository uses the Agent Skills model as an on-demand layer over the root `AGENTS.md` contract.

Skills live under `skills/<skill-name>/SKILL.md`. Each skill directory has a lowercase hyphenated name and a `SKILL.md` with the required `name` and `description` YAML frontmatter. Detailed references belong under the skill's `references/` directory and are loaded only when the skill is relevant.

## Available skills

- `nlweb-release` — release/build/promotion work; use when preparing a versioned bundle, tag, PyPI publication, provenance evidence, or rollback.
- `nlweb-provider-qa` — provider QA and conditional integration testing; use when validating optional retrieval backends or their environment/configuration boundaries.

The root `AGENTS.md` remains the canonical repository-wide contract. Skills are procedural, task-specific guidance and must not redefine compatibility or release policy.
