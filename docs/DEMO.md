# OpsPilot Demonstration Guide

**What should you run, what should you watch for, and how do you read what a live run does?**

A demonstration of OpsPilot is a demonstration of a live, model-directed system. The evidence path
is chosen by the model at each step, so two runs of the same incident can legitimately differ:
which capability is called first, whether retrieval is consulted, whether analysis asks to return
to gathering, and which outcome the run reaches are all the model's to decide within bounds the
code enforces. This guide therefore does not script a run. It says what each scenario is authored
to expose, what observable behavior is worth watching, and how to read the paths a run may take.
The properties being demonstrated are structural: they hold on every run, whichever path a
particular run takes. When a run does something this guide did not predict, that is usually the
demonstration working, and the sections below say how to read it.

Reach the screen locally per the README quickstart at `/investigation`, or at the hosted
deployment, which is behind sign-in.

---

## Reading the screen

The page has five regions.

**Start an investigation.** Pick one of the current incidents from the selector and press Start
investigation. That is the whole intake: there is no free-text entry, because the investigation
must reach its own conclusion rather than receive one. The selector offers the incidents presented
as current; others in the corpus are past incidents, and what a run may reach of them is their
write-ups, through retrieval, like any other knowledge.

**Activity.** The live feed. Each entry is one action the run took, rendered as
`[phase] action (status)` with a detail line: which capability was called and what came of it, why
gathering continued or stopped, what synthesis proposed, what grounding found, and that the record
was saved. The phases map onto the three roles and the Supervisor's deterministic steps:

| Phase | What is acting |
| --- | --- |
| `objective` | The Supervisor states what the investigation must establish |
| `gathering` | The Evidence Investigator proposes; the Supervisor authorizes; evidence access executes and admits |
| `synthesizing` | The RCA Analyst proposes the assessment |
| `grounding` | The Supervisor's deterministic gate checks the assessment against the admitted evidence |
| `persisting`, `delivering` | The Supervisor saves the completed record, then releases the brief |

Activity shows actions and their outcomes, not reasoning. There is no chain-of-thought anywhere on
the screen, by design: what you see is what the run did and what each step obtained, which is also
exactly what its telemetry records.

**Brief.** Empty while the run executes, then the dominant element the moment the terminal event
arrives. It leads with the outcome and what happened, then the candidate causes with what supports
and weakens each, then actions.

**Ask about this investigation.** Appears once a brief has been delivered. A question is answered
from the completed record alone, and the citations under an answer are checked by code against
that record: an answer that cited something the record does not carry is replaced by a refusal
saying so.

**Details.** The raw stream events, for anyone who wants to see exactly what the wire carried.

## Outcomes, before you run anything

The outcome is assigned by code from two facts the assessment holds, and reading a demo well
depends on knowing the vocabulary before the first run.

- **complete**: some candidate cause is established and no limitation was recorded. The evidence
  supported a conclusion and nothing material went unanswered.
- **partial**: some candidate cause is established and at least one limitation was recorded. A
  cause is established, and the brief also discloses what could not be checked. This deliberately
  over-reports: one small limitation makes an otherwise clean investigation partial, because the
  honest direction to err is disclosure.
- **inconclusive**: no candidate is established. The run observed real evidence and did not have
  enough support to settle a cause, and the brief says what is missing. This is a valid, grounded
  result, not an execution failure: an assistant that refuses to invent certainty is behaving
  correctly, and on some scenarios inconclusive is among the accepted answers.

Distinct from all three is a **failed execution**: the investigation itself could not complete.
Nothing was admitted, the assessment was unusable or could not be grounded even after the one
correction, the save failed, the deadline expired, or an unhandled error occurred. A failed
execution persists no record and the screen says which sanitized category it ended under. If you
see one, distinguish it from inconclusive: inconclusive is an answer, failed execution is the
absence of one.

## Moments worth pausing on

**A refused proposal.** If an activity entry reads `proposal refused`, stop the narration on it.
The model proposed an action, and model intent is not execution authority: deterministic code
refused the proposal, because it named an unregistered capability, repeated a question already
answered or a call already made, or asked for a call the budget no longer affords. The refusal is
recorded as the reason gathering ended, in the feed, which is bounded authority becoming visible.
Do not engineer a run to produce one, and do not treat its absence as a gap: a run with no
refusal is a run whose proposals were all authorized.

**Recommendation provenance.** In the brief's "What to do" section, every action names its source:
`(guidance: runbook:...)` when retrieved operational guidance shaped it, `(own judgement)` when
the analyst inferred it from what this investigation observed. This is one of the central things
to show. The system does not merely retrieve documents; it tracks whether a recommendation rests
on written operational practice or on inference, and says so on every action, checkably: a
guidance reference must resolve to a passage this run actually retrieved or grounding refuses the
assessment.

**A return to gathering.** If the feed shows `returned to gathering` between two assessment
entries, analysis named one material question and the kind of evidence that could answer it, and
deterministic code authorized one bounded return: the bound was unspent, a registered capability
supplies that evidence kind, the question had not already been answered, and the budget affords
the extra work. Gathering resumes seeded with that question, then synthesis runs once more. If
the analyst instead proceeds straight to grounding, it judged the existing evidence sufficient;
that is not a missing feature, and no run is promised a return. At most one happens per
investigation, by design.

**Retrieval.** If the investigator chooses `search_runbooks` or `search_past_incidents`, watch
what the passages do: they appear in the feed, may reshape what is checked next, and can surface
in the brief's history, knowledge, and action-provenance fields. Point out that retrieved
knowledge is background and precedent, never proof: a runbook cannot establish what happened in
this incident, and the grounding gate enforces exactly that. If retrieval does not occur on a run
where it was merely possible, nothing failed; the model judged the operational evidence
sufficient, and the run's citations will show it.

## The demonstration scenarios

### inc-004: adaptive investigation and a misleading correlation

The primary demonstration. Do not reveal the answer before the run.

The setup as the incident reports it: checkout-api is returning 500s shortly after this morning's
deployment. A deployment really did occur shortly before the symptoms, and the interesting
question is whether the investigation gathers enough discriminating evidence to accept or reject
that apparent correlation, rather than accepting it because it is temporally close.

Watch for:

- which capability is chosen first, and whether later choices react to what earlier ones
  returned;
- evidence accumulating on both sides of the deploy hypothesis: entries that strengthen it and
  entries that weaken it;
- a possible return to gathering, if the first synthesis cannot settle it;
- how the candidate causes are expressed: their ordering, their labels, and whether any is
  marked established;
- the recommendation, and whether it addresses the cause the evidence supports rather than the
  suspect the timing suggests;
- `grounding passed` before anything is delivered, and the outcome the run reports.

After completion, ask: was the morning deployment actually responsible, and what evidence supports
that conclusion? The answer comes from the completed record alone, with its citations checked.

### inc-007: retrieved precedent in a recurrence investigation

Order notifications are delayed again; queue depth is climbing and not draining. Relevant
historical material exists in the knowledge corpus for this one, which is what makes it the
retrieval scenario: this class of failure has happened before, and it was written down.

Watch for:

- retrieval, if the investigator selects it: it is one capability among nine, and nothing
  privileges it;
- references to a previous incident or postmortem appearing in the assessment's history and
  knowledge fields;
- current operational evidence staying separate from the historical knowledge: the queue metrics
  and worker logs carry the claims about today, the written record carries the precedent;
- whether the recurrence interpretation appears in the account;
- recommendations carrying `(guidance: ...)` provenance where written practice shaped them.

Suggested follow-up: has this happened before, and what should we do differently this time?

### inc-006: a contributor nothing points at

Reservation conflicts and oversells at checkout. Two conditions combined and neither alone explains
the oversell, so an account naming one of them has not finished.

Where the second one lives is what makes this worth watching. Stale cached availability sits on
services the incident already names. The reservation backlog sits on `inventory-reservation-worker`,
which the incident text does not mention, no alert names, and the alerting service's own logs,
metrics, and deployments do not reveal. Nothing pages on its queue depth, which is why a backlog
there goes unnoticed in the first place. So the question that reaches the second contributor cannot
be asked at the start: it becomes askable once something returns the worker's name, and the first
operational result that does is asking `inventory-api` what it depends on.

Watch for:

- whether the run asks what the alerting service depends on, and what it does with the answer;
- whether a capability is called against a service the run had not heard of when it started;
- whether the account ends with one contributor or two, and whether the recommended actions
  address both;
- a possible return to gathering, if the first synthesis finds the reservation side unexplained.

If the run reaches only the stale-cache half, read the brief for whether it says so rather than
presenting half an explanation as a whole one. An honest partial account is a correct result here.

Suggested follow-up: were there multiple contributing causes, and what led you to the second one?

### inc-005: a precedent that helps without settling anything

Checkout latency is up and sessions are dropping. The corpus holds a past incident where
`redis-cache` reached its memory ceiling and evicted cart sessions alongside cold entries, close
enough to this one to be worth reading and not close enough to settle it.

That distinction is the thing to draw out. A precedent can name the signals worth checking, the
hit rate and the eviction rate beside the latency, and can suggest what resolved it last time,
without establishing anything about today. Only current metrics do that, and the grounding gate
holds the line: a postmortem reference may support history or an action's provenance and may never
stand as current operational support.

Watch for:

- whether history is consulted at all, and if it is, whether the account treats it as a lead or as
  a finding;
- current cache metrics being read, and the account resting on those rather than on the precedent;
- one quieter honesty property this scenario has always carried: nothing was deployed in this
  incident's window, so watch how the run treats change evidence that genuinely is not there. A
  correct account reports that the change history was checked and held nothing, rather than
  skipping the question or inventing a deploy, and the checked absence is itself citable evidence.

If retrieval does not happen on a given run, nothing failed: the run exercised the adaptive loop
and grounding and did not exercise knowledge influence.

## When a live run varies

The demonstration should survive contact with a live model, and variation is mostly the point
showing itself:

- **A different tool order than last time**: evidence of model-directed adaptation. A fixed
  script would not vary.
- **No return to gathering**: the analyst judged the existing evidence sufficient. The return is
  a bounded possibility, not a promise.
- **No retrieval**: this run demonstrated the adaptive loop and grounding, and did not
  demonstrate knowledge influence; say which claims this run did and did not exercise rather
  than claiming failure.
- **A partial outcome**: a cause was established and a limitation is disclosed beside it. Read
  the "could not be established" section aloud; disclosure is the feature.
- **An inconclusive outcome**: the system declined to invent certainty. Show that the brief
  names what is missing and what the most useful next check would be.
- **A refused proposal**: bounded authority became visible; see above.
- **A failed execution**: the run itself could not complete, which is an infrastructure or
  runtime condition, not an investigative answer. Distinguish it from inconclusive, note that
  nothing was persisted, and run again.

## From behavior back to the design

Each observable behavior traces to a settled piece of the design, which is where the explanation
lives:

- who the three roles are, what each may decide, and where authority stops:
  [architecture.md](architecture.md);
- which component owns which responsibility, the capability surface, and the seams:
  [system-design.md](system-design.md);
- the run over time: gathering and continuation, the one return, grounding, the one correction,
  outcomes, and failure: [workflow-design.md](workflow-design.md);
- why evidence and retrieved knowledge are different trust classes, and what a reference is:
  [data-and-evidence.md](data-and-evidence.md);
- how the adaptive and retrieval claims are tested rather than asserted, and what the cheapest
  alternative to investigating would have concluded: [evaluation.md](evaluation.md).

The loop runs both ways: a behavior observed in a run is explained by the design, and the design
read first makes the run easier to interpret. What the recorded comparison runs actually showed is
in [engineering-notes.md](engineering-notes.md).
