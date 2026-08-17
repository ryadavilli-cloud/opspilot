# OpsPilot Code Guidelines

**What keeps the code from drifting away from the design?**

Short by intention. A developer should absorb this in one sitting. The design documents say what
the system is; this says how code stays faithful to it without turning every concept into a class.

---

## 1. Typed where it matters

Use ordinary Python typing and the existing domain objects by default. Create a dedicated class,
model, enum, protocol, or validator only when it:

- protects a trust or safety boundary;
- serializes or persists;
- holds a meaningful invariant no other layer already owns; or
- is genuinely reused in more than one place.

A conceptual interface in the design does not imply a request class and a result class. A table
row does not imply a type. Three strings do not need an enum. A validator that restates what
another layer already guarantees is deleted, not kept as defense in depth. Do not write a test whose
only job is to prove a redundant validator rejects an object normal code cannot build.

---

## 2. Strong invariants

These are the rules that must not be violated, and each has one owner in code:

- Models propose; deterministic code admits. No bound, evidence, outcome, or grounding result is
  written by a model.
- Evidence enters only through admission. Nothing else constructs an admitted observation.
- A tool result's execution outcome and completeness are separate, and an impossible pairing is
  rejected at the result boundary, once.
- Operational access is read-only on every path, including MCP.
- Structural admission of model output is structural only; grounding is the sole semantic owner of
  deliverability, is deterministic, and runs no model.
- Bounds live on investigation state, are set by code, and no agent widens them.
- Retrieved knowledge never stands as current operational support.
- The completed investigation is saved before the terminal event is emitted, and nothing is saved
  before completion.
- Investigations do not share mutable state.
- No secret in source, configuration files, images, logs, telemetry, health output, or artifacts.
- No hidden model reasoning reaches the engineer.
- No execution-plan vocabulary in code, comments, tests, configuration, or change descriptions.

---

## 3. Dependency direction

```text
  domain objects and rules   <-   agents, graph, admission, grounding   <-   adapters, API, cloud
```

Domain code imports no adapter, client, or cloud SDK. Adapters make no investigative decision:
whether evidence suffices, whether to continue, what the outcome is. That is the whole of it.

---

## 4. Testing

Deterministic guarantees have deterministic tests. Simple fakes and cassette replay stand in for
models, sources, and persistence; no test reaches a live service by accident, and the substitute is
planned when the seam is introduced. Tests own their state and pass in any order. Run the affected
tests, then the full gates. Delete a test with the behavior it protected; never keep one asserting
superseded semantics. Do not weaken lint, type, or test configuration to get green.

The type-checker's strict-override list only shrinks. A new module never joins it,
and a step that deletes a listed module deletes its entry in the same change.

Do not silence a type error with a broad cast, an escape-hatch annotation, an
ignore comment, or a weakened annotation. Fix the implementation or the contract
it violates.

---

## 5. Changes

One coherent claim per change. Replacement and deletion land together where practical, and
superseded code does not linger beside its replacement. No speculative abstraction, no reserved
field, no extension seam for a future that is not in the requirements. `uv` for everything;
formatting, lint, strict type check, and the deterministic test lane pass repository-wide before a
change is done.
