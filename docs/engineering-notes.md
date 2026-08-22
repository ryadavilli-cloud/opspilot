# OpsPilot Engineering Notes

**What did building, evaluating, and hosting OpsPilot establish that reading the design would
not?**

Historical run results are observations from the recorded and hosted runs that produced them, not
guarantees about any future run: a live model's choices are its own, and the durable claims are
about what the system makes possible, checkable, and safe.

---

## Components that worked alone were silent in composition

The strongest implementation lesson in the project. Four pieces of the telemetry path were
implemented, configured, individually tested, and present on the hosted revision, and none of them
participated in the live path:

- the wrapper that emits a span per model call was defined and tested, and never applied by the
  factory that builds the model;
- the environment name the revision reports was never set in the deployment template, so the
  hosted revision reported itself as local;
- the exporter the configuration named was never installed, because nothing at startup called the
  function that installs it, so a revision configured for telemetry emitted nothing while looking
  configured;
- the activity projection accepted the capability, the transport, and the outcome, and put none of
  them on the telemetry span, so a trace could say a capability step happened without saying
  which, over what, or whether it answered.

Each had a passing test. Every one of those tests constructed the component directly and asserted
its behavior in isolation; none asserted that the running composition uses it. The faults were
found by asking what a hosted trace would actually contain, not by any test failing.

The consequence was structural, not a bug fix. Startup now applies the configured exporter and
refuses to start when a setting names an exporter or provider that has no implementation, since
both faults resolve by silently falling back rather than by raising. The activity event and the
telemetry span are built in one call from the same stated facts (`stream/projection.py`), so the
feed and the trace cannot drift apart. And the deployment workflow queries the workspace for the
smoke run's spans by `investigation_id`, so a revision whose composition drops telemetry fails the
deploy rather than passing quietly.

## The two controlled comparisons

The comparisons exist to falsify the two central claims: that adaptation changes results, and that
retrieval influences reasoning rather than decorating output. Both were run live, with the
scenario, model deployment, prompt versions, configuration, and evidence environment held constant
and exactly one variable changed per comparison.

**Adaptive path against a fixed evidence order, on inc-004.** The fixed control issues the same
capabilities in a predetermined order chosen by how many steps have been taken and by nothing
observed, binding arguments from admitted evidence and making no model call. In the recorded
comparison runs, only the adaptive path reached `logs:checkout-api:evt-004-01`, evidence the
scenario's expectation requires. The result was reproduced across two separate runs, and the
comparison stopped at the first candidate scenario, which was the one the design had predicted
because its evidence path is contingent.

**Retrieval visible against retrieval withheld, on inc-007.** Withholding keeps retrieved passages
out of prompt assembly only: retrieval still executes, still spends its capability calls, and
still reaches the grounding gate and the completed record, which is what keeps the two conditions
comparable. In the recorded comparison the two conditions differed on every dimension the
comparison watches, each difference naming the condition it fell on: only the condition shown its
passages asked for `search_runbooks`, only the withheld condition asked for `get_incident` and
`search_past_incidents`, the leading candidates were two different accounts of the same incident,
and the interpretations stated and actions recommended each split between the sides.

Two report defects surfaced while getting there. An early version reported only that the
conditions differed, which cannot answer whether knowledge reaching reasoning changed anything;
the direction is the finding, and a test now requires every reported difference to name its side.
And a comparison whose shown-passages condition retrieved nothing is reported as a comparison
nobody could set up, never as no difference found.

## The Azure OpenAI rate ceiling

The chat deployment allowed 30k tokens and 30 requests per minute. One investigation pushes
roughly 30k to 54k tokens through in a burst across about eleven model calls, so a single run
could exceed the ceiling alone, and a controlled comparison needs two conditions through back to
back: every attempt was throttled even with nothing else touching the deployment, and no
comparison could complete until the ceiling was raised.

The distinction that made raising it an easy decision: this is a consumption deployment, billed
per token consumed. The per-minute figure is a ceiling on how fast work may proceed, not a
reservation of capacity, so raising it reserves nothing and adds nothing to the bill by itself.
It was raised to 300k tokens per minute, sized for the evaluation lane as the peak consumer, and
the template carries the value because the environment is reapplied from it on every deploy. A
throttled comparison condition is also no longer fatal to the report: it is recorded as a
condition that could not be obtained, with everything else intact. That guard was added after a
throttled call destroyed a complete evaluation run.

## Built-in authentication, diagnosed from the platform's side

Container Apps built-in authentication refuses a caller before the request reaches the container,
which means a misconfiguration is invisible from inside the application. Two settings were found
the hard way, and the platform reports both failures identically:

- the accepted audiences must include the bare client id, not only the `api://` identifier URI,
  because a registration issuing v2 tokens puts the client id in the token's audience claim;
- the issuer must be the `common` endpoint rather than `organizations`: both are multi-tenant,
  but the metadata `organizations` publishes declares its issuer as a template with the tenant
  left as a placeholder, which the platform does not substitute when validating a token presented
  directly.

Either mistake answers a valid token with a server error rather than a refusal. That is the tell:
the check failed, not the token.

Three objects had to exist outside the repository before any of the configuration meant anything,
because they are Graph or data-plane objects no template can create: the app registration, an app
role assigned to the principal the deployment workflow runs as (not authorization, and nothing
reads it; Entra will not issue a service principal a token for an API it holds no granted
permission on), and the client secret. The secret is the one secret the system holds; it lives in
a Key Vault and is read at runtime by the application's own identity, so it appears in no
template, parameter, or pipeline variable. An expired secret keeps deploying while every sign-in
fails, which is why the post-deploy smoke run authenticates rather than only checking health.

## The revision-handover streaming race

The post-deploy smoke run failed three times on revisions that were healthy and an application
that was fine. The deploy step returns once the new revision is provisioned, not once it is the
only one serving; the old revision drains for a while after that, and the smoke run starts an
investigation that streams for about two minutes. Begun into that gap, the stream is served by the
revision being retired and the connection closes without a terminal event, which the client
correctly reads as an abandoned run rather than a finished one.

The timeline settled the diagnosis: the revision that failed the gate was created eleven seconds
before the failing run began, and a re-run against the same revision with nothing else in flight
passed unchanged. The run was racing its own deploy.

The correction is a readiness check, not a pause. The workflow waits until exactly one revision is
active before smoking, a condition a deploy that changed nothing satisfies immediately, and
deploys are serialized, because a single application with a single revision cannot serve two runs
replacing it at once. A sleep of some hopeful length was considered and rejected: it narrows the
window without closing it and slows every deploy to pay for the rare one.

## A live model quoting the reference line, not the reference

The first hosted questions over a completed investigation were refused every time, and the
refusals were correct. The record digest rendered each citable reference with what it says beside
it on the same line; the model, instructed to cite exactly, quoted the entire line; and the entire
line is not a reference the record carries, so the deterministic citation check replaced every
answer. True of the string, false of the intent.

Deterministic tests never surfaced this because the fake and the cassette replay answer with
well-formed references by construction: no deterministic path asks a fresh model to decide where a
reference ends inside running prose. Only a live model asked the question that exposed the
representation.

The representation changed rather than the check: the digest now states the citable references on
their own lines, the prompt says the text beside a reference is there to read rather than to
quote, and a test holds the digest to that shape. The check that refused the answers is unchanged,
because it was right.

## The governed structured query's first real execution

The structured-query path existed structurally, was validated, translated, and tested by layer,
and had never truly executed end to end anywhere. Both recorded investigation runs proposed one,
and both proposals were refused before validation for using a key the structure does not have.
The cause was in what a caller was told: the offering described the predicate (a list of field,
operator, and operand, with three alternative operand keys named beneath) instead of showing the
object it must be. One run wrote `operand`, the other put a range in `value`, and each was a fair
reading of the description. Each form is now rendered as the object it must be, still derived from
the same enumeration the validator branches on, so what a caller is shown is what validation
enforces.

A second gap kept the deterministic lane from proving execution: the corpus fake matches query
parameters by the field they are named for, and a translated query carries positional parameter
names, so the fake can never answer a translated query. The deterministic lane therefore proves
validation, translation, and outcome mapping directly, by reading the emitted query text and bound
parameters, and the executing path was proven against the real store: on the deployed revision, an
investigation of inc-004 proposed a structure, validation accepted it, translation bound every
value as a parameter, and the store answered with nothing, which admission recorded as an
authoritative absence carrying a reference that resolves. A true empty answer, and a citable one.

## Retrieval was present and not meaningfully reached

Retrieval was implemented, registered, and proposable, and recorded runs never consulted it. The
finding that mattered is that this had three distinct causes, and only one of them was selection
behavior:

- **The offering described arguments, not purpose.** Each capability was presented by name and
  signature, so a role choosing among nine had names to go on. The offering now renders each
  capability's purpose from the implementation's own docstring beside its arguments, so the two
  cannot drift.
- **The budget was invisible.** The runtime claimed the investigator chose under bounds it could
  see, and it could not: calls were spent as though free, and a run worked down the offering
  rather than selecting from it, ending at the cap rather than when it had enough. With six
  capabilities offered a recorded run made six calls; with nine offered, nine, with the two
  retrieval capabilities sitting at the end of the list. Two consequences followed from the one
  cause: the analyst's request to return was declined for lack of room rather than on its merits,
  and retrieval was reachable without being consulted. The investigator is now told how many
  calls it has left and that it cannot use everything.
- **Retrieved passages never reached the analyst.** They were threaded into the synthesis call and
  the message never rendered them, so every knowledge field of the assessment would have stayed
  empty however well retrieval was selected. This was plumbing, and it would have made any amount
  of prompt work on selection look ineffective.

None of this was a vector-search quality problem, and treating it as one would have fixed nothing.
After the three corrections, a recorded run of the recurrence scenario consulted the runbooks of
its own accord and the assessment cited four passages, two of them behind recommended actions; a
hosted run of inc-007 chose `search_runbooks` as one entry among nine, was returned to gathering
once, and delivered a brief resting partly on `runbook:service-bus-backlog` and
`architecture:service-dependency-map`. A hosted run on the same tree chose no retrieval at all,
and both runs are recorded, because both are true.

## Predicting a model's choices is the fragile half of a proof

The return to gathering was expected to demonstrate on inc-004, the incident authored so a first
pass cannot close it. Recorded against the deployed chat model, inc-004 asked for nothing further
and closed on what it had, while inc-005 asked for one more check and was granted the return. Both
recordings were committed as taken rather than re-rolled until one matched the plan. The same
pattern repeated with retrieval: the recurrence scenario was expected to surface its postmortem,
and the hosted brief cited a runbook and an architecture note instead.

In each case the prediction was wrong and the behavior was right. Which incident a model finds
unsettled, and which written record answers it, are properties of the model and the corpus, not of
the design. The consequence runs through the proofs: deterministic tests hold the mechanisms still
and prove them exactly, hosted verification proves the envelope and the delivered brief, and no
proof asserts that a named scenario will exhibit a model-directed behavior on demand.
