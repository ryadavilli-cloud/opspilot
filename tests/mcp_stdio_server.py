"""The shipped MCP server, bound to the authored corpus, as a process a client can spawn.

Not a stand-in for the server: `build_server` is the application's own, and the only thing this
file decides is which records it reads, so the protocol under test is the protocol that ships. It
lives beside the tests because choosing the corpus is a test's business, and it is a module rather
than an inline command so the client spawns something readable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_operational_records import corpus_records  # noqa: E402

from opspilot.mcp.server import build_server  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

if __name__ == "__main__":
    build_server(ToolService(corpus_records())).run(transport="stdio")
