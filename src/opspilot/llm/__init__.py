"""The model seam: one chat-model contract, and the factory that answers it.

Every role talks only to `ChatModel` (see `base.py`), and `build_chat_model` (see `client.py`)
answers with the live Azure adapter or cassette replay. Nothing here imports a provider SDK at
module load, so the lean runtime image and the CI lane import this package without the optional
`llm` dependency group installed.
"""
