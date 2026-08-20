"""The one injection seam the investigation runner exposes to the offline harness.

Controlled comparisons need to change exactly one thing about a run and watch what follows. That
cannot be done from outside: the two variables worth changing, what decides the next action and
whether retrieved passages reach reasoning, are both interior to the run. So the runner exposes one
seam for them, and one only.

What it deliberately is not: an API parameter, a configuration setting, or persisted state. It is
passed with the other run dependencies, which the HTTP route constructs itself and never takes from
a request, so nothing a caller can send reaches this. A setting would put it in the deployed
environment's reach; persisted state would let one run leave it behind for another.

Absent is the ordinary case and the default, so a run that was given no harness behaves exactly as
a run that could not have been given one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# The run-configuration key the seam travels under, beside the model, the tool service, and the
# record store. One key holding one object, because these are two levers of one seam rather than
# two independent settings that could drift apart.
HARNESS = "harness"


@dataclass(frozen=True)
class Harness:
    """The two substitutions a controlled comparison may make, and nothing else.

    `next_action` replaces what decides the investigation's next step. It takes and returns exactly
    what the investigator's own proposal does, so the run around it cannot tell the difference:
    the same authorization, the same bounds, the same admission.

    `withhold_knowledge` keeps retrieved passages out of the prompts the roles are given, while
    retrieval still runs, still costs what it costs, still records its operations, and still reaches
    the completed record. Withholding the influence rather than the retrieval is what keeps the two
    conditions comparable, because the activity and the tool counts stay the same and the only
    difference is whether the knowledge reached reasoning.
    """

    next_action: Callable[..., Any] | None = None
    withhold_knowledge: bool = False


def knowledge_for_prompts(knowledge: list[Any], harness: Harness | None) -> list[Any]:
    """What a role is shown of what the run retrieved.

    Only prompt assembly asks this. The grounding gate and the completed record read the knowledge
    set directly, because withholding there would not be a comparison of reasoning but a lie about
    what the run held.
    """
    if harness is not None and harness.withhold_knowledge:
        return []
    return knowledge
