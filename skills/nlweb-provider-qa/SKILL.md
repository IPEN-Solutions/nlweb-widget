---
name: nlweb-provider-qa
description: Validate nlweb-widget optional retrieval providers, embeddings, and configured backend behavior. Use when checking provider configuration, operational tests, conditional skips, or provider-specific failures.
---

# Provider QA

1. Identify the provider selected by `NLWEB_RETRIEVAL_STORE`.
2. Verify its optional dependency is installed through the declared package extra.
3. If the provider is unconfigured, the conditional integration test should skip.
4. If explicitly configured, initialize the real backend and exercise write/retrieve/cleanup behavior; connection or runtime errors are failures.
5. Keep provider test state isolated from production/example state, including labels, collections, tables, indexes, and vector dimensions.
6. Keep embedding dimensions configuration-driven.
7. Do not require a live LLM for retrieval-provider QA.

Provider contracts are owned by the widget; backend-specific objects must remain behind the provider boundary.
