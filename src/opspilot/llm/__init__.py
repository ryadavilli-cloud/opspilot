"""LLM seam — a provider-agnostic chat-model interface and its factory.

The diagnosis core talks only to `ChatModel` (see `base.py`); vendors are resolved by
`build_chat_model` (see `client.py`). Nothing here imports a vendor SDK at module load, so the lean
runtime image and the CI core lane can import this package without the optional `llm` dependency
group installed.
"""
