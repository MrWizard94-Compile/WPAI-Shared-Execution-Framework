# Stage 1.2 audit follow-up

## Stage 0B archive exception

The seven `home_account` matches refer to `records/grok.json` inside the original local `outputs/stage-0b-mcp-probe.zip`. The exact nested member has seven occurrences of the local Windows profile name in path strings. This is existing local path-identifying information. The published archive contains `LOCAL_USER` in those positions. Applying precisely those seven replacements to the original member reproduced the published member bytes, with zero matches left. Neither archive was edited. The published copy is the previously approved path-substituted archive.

| Artifact | SHA-256 |
|---|---|
| Original local archive | `b59081f4feab80c7a0c4eee1f582b0108c3815dec7c4a3a22fddcde2a56a3439` |
| Published archive | `5b960e0eff88baefcd0623ab0890f9db226be712b8d6a475631e3371536747dc` |

The count and location in the prior scan stand. This follow-up distinguishes the local source from the Git blob at accepted `main`. It neither publishes the path-account value nor provides access to the original archive. No active credential or sensitive provider account value was identified in this member or the reviewed Stage 1.2 payload. The benchmark records retain categorical authorization and synthetic operation data only.

## Protocol schema evidence

The upstream revision remains `024d5255eb4466ba4fab21e044b5ba84d6a79327`. The exact JSON Schema hashes below identify the upstream full-schema evidence against which Stage 1.1 representative outputs were validated. Stage 1.2 retained the version-derived regression tests and executed both synthetic arms on all three revisions entirely offline. This covers the advertised server subset.

| Revision | Upstream schema SHA-256 |
|---|---|
| `2025-06-18` | `af845e7e5b9d27107d1690f0936022546177a1403e63ffb11470135b296a2e01` |
| `2025-11-25` | `268a5f82ba70fd7e4b6dc4aa1e64f116f74b4d0edcb69dc046829c79dd4e97e7` |
| `2026-07-28` | `2e3a8972df2154523045cd33e388f8856b3505cbcd7d38d048f3cd3cf6c5d937` |

An offline full-schema CI gate is deferred. The three complete documents total 464,582 bytes and require a validator that handles both Draft 7 and 2020-12. The supported 3.10 environment has no such dependency. A general-purpose validator or an optional CI dependency deserves a separate approval and provenance review. The current CI remains network-independent for tests. [June 2025 schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/024d5255eb4466ba4fab21e044b5ba84d6a79327/schema/2025-06-18/schema.json) · [November 2025 schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/024d5255eb4466ba4fab21e044b5ba84d6a79327/schema/2025-11-25/schema.json) · [July 2026 schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/024d5255eb4466ba4fab21e044b5ba84d6a79327/schema/2026-07-28/schema.json).
