"""5b — the durable checkpointer seam. Proves the factory routes backends (unknown fails loud), and
that the SQLite saver's checkpoint survives a *fresh* saver instance on the same store — i.e. it
persists across a process restart, the property 5c's interrupt-resume and 5d's 202-durability need.

ML-free: SQLite is file-backed and needs no model or Azure. The `cosmos` backend is validated only
for its config guard (a live Cosmos test would need Azure + the optional `checkpoint` group)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from opspilot import config
from opspilot.checkpoint import build_checkpointer


class _S(TypedDict):
    value: str


def _tiny_graph(checkpointer):
    """A one-node graph that stamps a known value — the smallest thing that checkpoints."""
    g = StateGraph(_S)
    g.add_node("set", lambda _s: {"value": "persisted"})
    g.add_edge(START, "set")
    g.add_edge("set", END)
    return g.compile(checkpointer=checkpointer)


def _echo_graph(checkpointer):
    """Like `_tiny_graph`, but the stamped value derives from the input, so a checkpoint read
    back proves *which* caller wrote it. That is what the concurrency test needs."""
    g = StateGraph(_S)
    g.add_node("stamp", lambda s: {"value": f"{s['value']}-done"})
    g.add_edge(START, "stamp")
    g.add_edge("stamp", END)
    return g.compile(checkpointer=checkpointer)


def test_none_backend_is_no_checkpointer():
    assert build_checkpointer("none") is None


def test_memory_backend_builds_a_saver():
    from langgraph.checkpoint.memory import MemorySaver

    assert isinstance(build_checkpointer("memory"), MemorySaver)


def test_unknown_backend_fails_loud():
    with pytest.raises(ValueError, match="unknown checkpointer backend"):
        build_checkpointer("redis")


def test_cosmos_requires_an_endpoint(monkeypatch):
    # The config guard must fire before the optional import, so this holds even without the
    # `checkpoint` group installed (as in CI).
    monkeypatch.setattr(config, "COSMOS_ENDPOINT", "")
    with pytest.raises(ValueError, match="AZURE_COSMOS_ENDPOINT"):
        build_checkpointer("cosmos")


def test_sqlite_checkpoint_survives_a_fresh_saver(tmp_path):
    """write → (new saver on the same file, i.e. a new process) → the checkpoint is still there."""
    db = str(tmp_path / "checkpoints.sqlite")
    cfg = {"configurable": {"thread_id": "inc-042"}}

    # Instance A: run the graph, which writes a checkpoint for thread inc-042 to the sqlite file.
    saver_a = build_checkpointer("sqlite", sqlite_path=db)
    result = _tiny_graph(saver_a).invoke({"value": "initial"}, cfg)
    assert result["value"] == "persisted"

    # Instance B: a brand-new saver + graph over the SAME file — a restarted process. The checkpoint
    # written by A must be readable here, proving durability (not just in-process memory).
    saver_b = build_checkpointer("sqlite", sqlite_path=db)
    snapshot = _tiny_graph(saver_b).get_state(cfg)
    assert snapshot.values["value"] == "persisted"
    assert snapshot.config["configurable"]["thread_id"] == "inc-042"


def test_a_fresh_thread_has_no_state(tmp_path):
    """The durability is per-thread: an unrelated thread id sees an empty checkpoint, not A's."""
    db = str(tmp_path / "checkpoints.sqlite")
    _tiny_graph(build_checkpointer("sqlite", sqlite_path=db)).invoke(
        {"value": "initial"}, {"configurable": {"thread_id": "inc-042"}}
    )
    other = _tiny_graph(build_checkpointer("sqlite", sqlite_path=db)).get_state(
        {"configurable": {"thread_id": "does-not-exist"}}
    )
    assert other.values == {}


def test_concurrent_threads_share_one_sqlite_saver(tmp_path):
    """G-37: the dev-path shape. ONE process-wide saver behind ONE compiled graph (api.py's
    `get_graph()` singleton), driven from many threads at once, because FastAPI runs the sync
    background investigation jobs on its worker threadpool.

    The saver holds a single `check_same_thread=False` connection, so this is the regression
    test for `SqliteSaver` losing its internal serialization (see `checkpoint.py`). Verified to
    discriminate: with that lock stubbed out, every worker here faults with an
    `sqlite3.InterfaceError`. Each worker asserts on its OWN namespace, so a cross-thread write
    fails the assertion rather than passing by coincidence.
    """
    saver = build_checkpointer("sqlite", sqlite_path=str(tmp_path / "checkpoints.sqlite"))
    graph = _echo_graph(saver)

    workers, turns = 8, 5
    start = threading.Barrier(workers)  # release all threads together: maximize the overlap
    errors: list[Exception] = []

    def drive(i: int) -> None:
        cfg = {"configurable": {"thread_id": f"inc-{i}"}}
        try:
            start.wait(timeout=10)
            for turn in range(turns):
                result = graph.invoke({"value": f"inc-{i}-turn-{turn}"}, cfg)
                assert result["value"] == f"inc-{i}-turn-{turn}-done"
        except Exception as exc:  # noqa: BLE001 (collected so the assertion reports the real fault)
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(drive, range(workers)))

    assert errors == [], f"concurrent checkpoint writes faulted: {errors!r}"

    # Every namespace survived holding its own last turn: no lost or cross-written checkpoints.
    for i in range(workers):
        snapshot = graph.get_state({"configurable": {"thread_id": f"inc-{i}"}})
        assert snapshot.values["value"] == f"inc-{i}-turn-{turns - 1}-done"


def test_hitl_interrupt_resumes_across_a_fresh_checkpointer_instance(tmp_path):
    """5c property: the real investigation graph, over real data, pauses at hitl_gate's
    interrupt() on one sqlite-backed instance; a brand-new instance over the SAME file (a
    simulated process restart) resumes it with a human decision and reaches the byte-exact
    approved report."""
    from fake_operational_records import corpus_records
    from langgraph.types import Command

    from opspilot.graph import _initial_state, build_graph
    from opspilot.tools.service import ToolService

    db = str(tmp_path / "checkpoints.sqlite")
    alert = {
        "incident_id": "inc-004",
        "summary": "checkout-api returning 500s shortly after this morning's deployment.",
    }

    # Instance A: run to the hitl_gate pause; the checkpoint is written to the sqlite file.
    graph_a = build_checkpointer("sqlite", sqlite_path=db)
    cfg_a = {
        "configurable": {
            "tool_service": ToolService(corpus_records()),
            "thread_id": "inc-restart-test",
        }
    }
    paused = build_graph(graph_a).invoke(_initial_state(alert), cfg_a)
    pending = paused["__interrupt__"]
    report_hash = pending[0].value["report_hash"]

    # Instance B: a brand-new saver + graph over the SAME file — a restarted process. hitl_gate is
    # the only node that re-executes on resume, so no ToolService is needed here.
    graph_b = build_checkpointer("sqlite", sqlite_path=db)
    cfg_b = {"configurable": {"thread_id": "inc-restart-test"}}
    result = build_graph(graph_b).invoke(
        Command(
            resume={
                "decision": "approve",
                "approver": "ops-oncall",
                "edits": None,
                "submitted_report_hash": report_hash,
            }
        ),
        cfg_b,
    )
    assert result["report"].content_hash() == report_hash
    assert result["approval"]["approved_report_hash"] == report_hash
