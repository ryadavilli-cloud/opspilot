"""The judge's model, constructed with the judge's fixed settings already bound.

The one entry point the evaluation runner imports. The evaluation decides that the judge is this
model; there is no setting choosing a judge provider, because a second way to be wrong about
which model judged is worse than none.

Construction goes through the model factory rather than beside it, so the judge's calls are
traced exactly like every other model call in the system. A client built outside the factory
would be the only untraced model path there is. The factory can build this adapter and
configuration cannot select it, which is what keeps the judge's model unreachable from the
investigation graph.
"""

from __future__ import annotations

from opspilot import config
from opspilot.llm.base import ChatModel
from opspilot.llm.client import build_chat_model


def build_judge_model() -> ChatModel:
    """The judge's model, or a refusal naming the setting that is missing.

    Raised rather than defaulted: a judge that silently ran on some other model would produce
    verdicts nobody can attribute, and the caller already knows how to report a judge that could
    not be built as a judgement that did not run.
    """
    if not config.AZURE_CLAUDE_ENDPOINT:
        raise ValueError("AZURE_CLAUDE_ENDPOINT is unset; the judge has no endpoint to call")
    if not config.AZURE_CLAUDE_DEPLOYMENT:
        raise ValueError("AZURE_CLAUDE_DEPLOYMENT is unset; the judge has no deployment to call")
    return build_chat_model("claude", deployment=config.AZURE_CLAUDE_DEPLOYMENT)
