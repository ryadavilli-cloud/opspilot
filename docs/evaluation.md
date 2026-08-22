# OpsPilot Evaluation

**How do we show that OpsPilot's important claims hold, that development was deliberate, and that
the capstone demonstrates how agentic systems are evaluated?**

This document owns evaluation technique. Evaluation runs offline over completed investigations,
informs rather than gates, and certifies nothing about production suitability. It is not a
platform: one runner, authored expectations, deterministic checks, two controlled comparisons, one
LLM judge, one report.

---

## 1. Principles

**Offline and advisory.** Evaluation never participates in a live run, never confirms a diagnosis
at runtime, and never blocks delivery. Its results inform a change; they do not gate a merge.

**Deterministic before model-assisted.** Anything code can establish, code establishes and reports
pass or fail. The judge scores only qualities that need semantic judgement, and a deterministic
result is never overridden by the judge.

**The completed investigation is the unit.** Evaluation reads the persisted record and its
telemetry. It does not score isolated model messages.

**Named failures, no aggregate.** Results are per scenario, each failure named. No composite score,
no threshold set before a measured baseline exists, and no published figure is a commitment.

**Reproducible enough to compare.** Cassette replay keeps deterministic runs deterministic; each
run records the configuration it ran under, so a prompt or model change is compared by running the
same set again.

---

## 2. Inputs

**Scenarios.** The seven authored incidents and the benign fixture. The seven span five
overlapping incident families: resource saturation, downstream or external dependency failure,
deployment regression, cache failure or stale data, and queue backlog or consumer failure. Families
deliberately share alerts and visible symptoms, so a cause is distinguished by evidence and never
by alert name alone. The fixture represents the benign-or-transient class the seven do not
naturally contain; it is evaluation corpus, not an eighth authored incident.

**Authored expectations.** One per scenario, kept small: the expected cause; acceptable
alternatives; the evidence references a correct investigation must reach; evidence deliberately
absent from the corpus that a correct investigation must disclose rather than assert; the outcomes
the scenario accepts; and the behavior the scenario exists to test. Where a scenario expects
retrieved knowledge to matter, the expectation says how.

**Completed investigations and telemetry.** Replayed for determinism; live where a comparison needs
it.

---

## 3. Scenario behavior

For each scenario, the report says whether the investigation reached a reasonable diagnosis (the
expected cause leads on a clear incident, appears among the candidates on an ambiguous one),
handled ambiguity honestly (a red herring examined and cleared, not accepted), recognized multiple
contributors where the expectation names them, admitted insufficient evidence where appropriate,
and recommended no immediate action on the benign fixture.

Two of these are mechanical, read from the record against the expectation: the outcome is one the
scenario accepts, and an affirmative no-immediate-action entry is present where the expectation
requires one. The rest compare prose candidates against an expected cause and are semantic; they
are decided by the one offline judge path (section 7) against the expectation and reported as
categories, never as a deterministic pass or fail. The mechanical layer stays mechanical.

---

## 4. Deterministic correctness

For each completed investigation, mechanically: every operational-support reference resolves in the
record's admitted evidence and every knowledge reference in its retrieved knowledge; `what_happened`
and every established candidate have admitted operational support, and no knowledge reference
stands as current operational proof; no operation attempted was a write, checked from the record's
operations list against the registry; and deliberately absent evidence is disclosed, as a recorded
absence or as a limitation. These reuse the runtime's own reference resolver and grounding function
rather than reimplementing them.

---

## 5. Adaptive value

One controlled comparison. The evaluation harness runs the same scenario twice: once normally, and
once with the Evidence Investigator's next-action source replaced by a fixed script over the same
tools in a predetermined order. The comparison reports whether the adaptive path reached a
meaningfully better result: a correct cause the fixed path missed, a red herring the fixed path
accepted, or required evidence only the adaptive path reached.

The scenario is chosen empirically. inc-004 is the likely candidate because its evidence path is
contingent, but no scenario is declared to satisfy this until the comparison has been run and shows
the difference. One or a few scenarios suffice; this is a falsification test, not a benchmark.

---

## 6. Retrieval influence

One controlled comparison on inc-007, the scenario authored so that a postmortem's recurrence
signature changes the investigation's path. Two runs of the same investigation: normally, and with
retrieval still executing and still recorded but its passages withheld from the agents' prompts.
Withholding influence rather than retrieval keeps the activity and tool counts comparable, so the
only difference is whether the knowledge reached reasoning.

Held constant across the two runs: the scenario, the model deployment and version, the prompt
versions, the runtime configuration, and the evidence and tool environment. The one experimental
variable is whether retrieved passages reach reasoning. Because the model's input differs between
the two conditions, the model's response must be allowed to differ: the comparison uses live model
calls, or responses recorded separately for each condition. It must not replay one identical
cassette response across both runs, which would erase the variable being tested. Cassette replay
remains the determinism mechanism for ordinary evaluation and tests; it is not used to make the two
conditions of a controlled comparison return the same model output. The same rule applies to the
adaptive-value comparison wherever the fixed path changes what a model call is asked.

The comparison passes when at least one of the following differs in the direction the expectation
names: a capability the Evidence Investigator proposed, the leading candidate or its label, an
interpretation the assessment states, or an action recommended. Retrieval is not required on
scenarios that do not need it, and no scenario is penalized for not retrieving.

Both comparisons use the one internal injection seam the investigation runner exposes to the
harness. It is not an API parameter, not configuration, and not persisted state.

---

## 7. The judge

One offline model-assisted judge, using its own judge model rather than the runtime's chat
deployment (the choice and its cost are D-005 in `decisions.md`) and one authored
rubric. It reads the brief, the incident summary, and the expectation, and returns a category for
each of four qualities: whether the brief is useful and coherent; whether uncertainty is
communicated appropriately; whether the diagnosis is well explained in context; and whether the
recommendations fit the established situation. It also decides the semantic diagnosis matching
section 3 names, against the expectation. Categories, not scores. It runs after the deterministic
checks and its result is reported beside them, never combined into one number. It is never a
runtime authority. There is one judge path, no ensemble, and no debate.

---

## 8. The runner and the report

One runner: for a chosen scenario set, obtain or replay the completed investigations, apply the
scenario and correctness checks, run the two comparisons where the set includes their scenarios,
call the judge, and write one report. For the benign fixture the runner invokes the investigation
runner directly with the fixture's incident context; the fixture is not selectable in the product
interface. The report is one document per run: per-scenario results with named failures, the two
comparison results with what differed, judge categories, and usage figures. It records the
configuration identity it ran under. Where the report lives, and which scenario is the fast one, are conventions rather than
decisions.

Cadence: the fast scenario on a meaningful change; the full set before a milestone. Both are
advisory.

---

## 9. What is not here

No precision or recall as a mandated metric; no numeric release gate; no repeated-run subsystem
beyond running the same set again; no per-class report schema as a contract; no evaluator agents;
no verification that the MCP path matches the direct path, which is a deterministic test of that
capability's own semantics, not an evaluation dimension.
