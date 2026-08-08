# ADR — Model provider & routing: two adapters, tiered, hosting-aware (G-45)

**Status:** accepted — `anthropic_foundry` adapter proposed/unbuilt · **Stage:** 8 · **Closes:**
[G-45](./status.md#g-45) · **Companion to** `deployment.md` §11 (provider seam, models) and
`decisions.md` §13.1 ("LLM provider adapter").

Records the *model-provider/routing* decision that code-guidelines §19 requires an ADR for. The
`ChatModel` seam and the tier→model profile live in `deployment.md` §11; this ADR is the *why the two
providers do not compose*, and the *adapter + tiering + hosting-location decision*.

---

## Context

`deployment.md` §11's model table named the production tiers as **Claude on Microsoft Foundry**, while
the provider seam claimed the production path was **`AzureOpenAI`**. These do not compose. Claude on
Foundry is served through Anthropic's **Messages API** (`/v1/messages`, the `AnthropicFoundry` client) —
a different request/response shape from Azure OpenAI chat-completions, not a base-URL swap. The
deployed demo runs a gpt-class model through `AzureOpenAI` and works; the *target* Claude tiers cannot
use that adapter at all, so the `ChatModel` seam has only ever been exercised against OpenAI shapes.

## Decision

**Two provider adapters behind one `ChatModel` contract:**

- **`azure_openai`** — `AzureOpenAI` chat-completions, keyless via managed identity (what the demo runs).
- **`anthropic_foundry`** — Anthropic Messages API on Foundry, Entra-auth, keyless — the adapter the
  Claude tiers require, not yet built.

The `ChatModel` contract **normalizes both surfaces** into one shape and a **normalized usage
record** — the per-concern comparison table (tool calls, structured output, usage, refusal,
reasoning, token counting, caching, content model) lives in [`deployment.md` §11](./deployment.md)
and is not restated here.

**Severity tiering** is config-bound (`PROD_MODELS[CHEAP|STANDARD|PREMIUM]`, premium flag-gated off),
not architecture; the doc names tiers and the selection policy, never a model id. **Hosting location**
(Azure-hosted vs Anthropic-through-Foundry) is declared **per tier** — it governs data residency and is
not derivable from the model id.

## Consequences

- **`tiktoken` is not a provider-neutral cost layer** — it is the OpenAI tokenizer and under-counts
  Claude/Qwen. Cost estimation uses the model's own `count_tokens` pre-call and provider-reported usage
  post-call, both flowing into the normalized usage record.
- Claude-on-Foundry needs its own Azure resource + role grant; `infra/main.bicep` provisions only the
  Azure OpenAI account today.
- Landing the adapter forces a **re-baseline**: cassettes key on the model/hosting (part of the cassette
  manifest, `evaluation.md` §10), so the eval scorecard must be re-recorded on the production surface.
- Mid-run tier switching stays out (§5): it would split one run across two cassette manifests and break
  per-implementation baselines.
