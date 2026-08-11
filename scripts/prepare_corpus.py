"""Corpus preparation: load, chunk, embed, and index the RetailEase corpus into Cosmos.

This is an offline setup task, not a component. It participates in no turn, nothing in the runtime
path imports it, and its absence is a deployment-time failure rather than a turn-time one. It runs
as a setup principal with write access the application deliberately does not have: the application
holds read-only on the RetailEase database, enforced by the Cosmos role assignment rather than by
anything in this file.

It lives under `scripts/` rather than `src/opspilot/` so that "reachable from no runtime code" is a
property of the layout rather than a convention. Tests import it by path, the way the answer key's
`build_goldens.py` is already imported.

Usage:
    uv run python scripts/prepare_corpus.py            # seed both containers
    uv run python scripts/prepare_corpus.py --dry-run  # shape documents, write nothing, no Azure

Determinism matters: a re-run must produce the same passages and the same identifiers, so every
derived collection is sorted and every id is content-derived rather than positional or timestamped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from opspilot.retrieval.corpus import chunk, load_docs  # noqa: E402

DATA = REPO_ROOT / "data"
SYN = DATA / "synthetic"

# `kind` in the KB frontmatter already maps one-to-one onto the three routed logical collections,
# so the category field is that value rather than a second vocabulary invented here.
KNOWN_CATEGORIES = ("runbook", "architecture", "postmortem")

# Identifier extraction targets, fixed by D-003: a service name, an error code, or a deployment
# identifier. Deliberately three narrow patterns rather than general entity recognition, because
# the point is that exact matching is deterministic rather than dependent on tokenization.
_DEPLOY_ID = re.compile(r"\bdep-\d{8}-\d{2}\b")
_ERROR_CODE = re.compile(r"\b(?:[45]\d{2}|[45]xx)\b")

# Cosmos rejects '/', '\\', '?', and '#' in a document id. The chunker separates a passage from its
# document with '#', so the id is translated on the way in rather than the chunker being changed:
# '#' is the established in-repo notation and retrieval fixtures already use it. The mapping is
# one-to-one and reversible, and the untranslated value is kept as `chunk_id` so nothing is lost.
_ID_TRANSLATION = str.maketrans({"#": "~", "/": "_", "\\": "_", "?": "_"})


def cosmos_id(chunk_id: str) -> str:
    """A chunk id Cosmos will accept, derived deterministically from the repository's own."""
    return chunk_id.translate(_ID_TRANSLATION)


def topology_entities() -> tuple[str, ...]:
    """Every service, infra, and external entity name, longest first so that a longer name is
    matched before any shorter name it contains."""
    topology = yaml.safe_load((DATA / "answer_key" / "topology.yaml").read_text(encoding="utf-8"))
    names = [
        entry["id"]
        for group in ("services", "infra", "externals")
        for entry in topology.get(group, [])
    ]
    return tuple(sorted(names, key=len, reverse=True))


def extract_identifiers(text: str, entities: Iterable[str]) -> list[str]:
    """The identifiers a passage mentions, as exact strings retrieval can match on.

    Sorted, so a re-run over unchanged text produces an unchanged field.
    """
    found: set[str] = {name for name in entities if name in text}
    found |= set(_DEPLOY_ID.findall(text))
    found |= {code.lower() for code in _ERROR_CODE.findall(text)}
    return sorted(found)


def _postmortem_date(doc_id: str, incident_dates: dict[str, str]) -> str | None:
    """Postmortems carry their incident's date; runbooks and architecture docs have none.

    Absent stays absent. The deterministic promotion rule reads time metadata "where available",
    so a missing date is a legal state, and inventing one from file mtime or git history would
    silently skew any time-window promotion.
    """
    if not doc_id.startswith("postmortem:"):
        return None
    return incident_dates.get(doc_id.split(":", 1)[1])


def incident_dates() -> dict[str, str]:
    incidents = json.loads((SYN / "incidents.json").read_text(encoding="utf-8"))["incidents"]
    return {record["incident_id"]: record["opened_at"] for record in incidents}


def knowledge_documents(
    kb_dir: Path | None = None, distractor_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Every knowledge passage, shaped for the container but not yet embedded.

    Distractors are loaded alongside real knowledge and are indistinguishable at query time. That
    is the point: retrieval precision counts how many retrieved passages were correct, so a corpus
    in which every document is a correct answer to something measures nothing. Their provenance is
    recorded honestly, but nothing in the query path may branch on it.
    """
    entities = topology_entities()
    dates = incident_dates()
    docs = load_docs(
        kb_dir or DATA / "kb",
        distractor_dir if distractor_dir is not None else DATA / "distractors",
        include_distractors=True,
    )

    out: list[dict[str, Any]] = []
    for doc in docs:
        for passage in chunk(doc):
            out.append(
                {
                    "id": cosmos_id(passage.chunk_id),
                    "chunk_id": passage.chunk_id,
                    "category": passage.kind,
                    "doc_id": passage.doc_id,
                    "title": doc.title,
                    "text": passage.text,
                    "services": sorted(passage.services),
                    "date": _postmortem_date(passage.doc_id, dates),
                    "identifiers": extract_identifiers(passage.text, entities),
                    "provenance": {
                        "source": "data/kb" if not doc.is_distractor else "data/distractors",
                        "doc_id": passage.doc_id,
                    },
                }
            )
    out.sort(key=lambda d: d["id"])
    return out


def _records(name: str, key: str) -> list[dict[str, Any]]:
    return json.loads((SYN / f"{name}.json").read_text(encoding="utf-8"))[key]


def operational_documents() -> list[dict[str, Any]]:
    """Every operational record, shaped for the hierarchically partitioned container.

    `kind` and `service` are the two partition levels. Incidents and dependency edges carry no
    service, which Cosmos permits: they sit under an undefined second level and are reached by
    kind-scoped queries, which is how they are actually queried.
    """
    out: list[dict[str, Any]] = []

    for record in _records("incidents", "incidents"):
        out.append({**record, "id": record["incident_id"], "kind": "incident"})

    for record in _records("alerts", "alerts"):
        out.append({**record, "id": record["alert_id"], "kind": "alert"})

    for record in _records("deployments", "deployments"):
        out.append({**record, "id": record["deploy_id"], "kind": "deployment"})

    for edge in _records("dependencies", "edges"):
        out.append({**edge, "id": f"{edge['from']}->{edge['to']}", "kind": "dependency"})

    for line in (SYN / "logs.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        out.append({**record, "id": record["event_id"], "kind": "log"})

    for series in _records("metrics", "series"):
        # The incident is part of the identity, not decoration. The corpus carries one series per
        # (service, metric, incident): 189 series over only 27 distinct service/metric pairs. Keying
        # on service and metric alone would upsert 189 documents down to 27 and silently discard
        # 86% of the metric evidence, with no error at write time.
        scope = series.get("incident_id") or "ambient"
        out.append(
            {
                **series,
                "id": f"{series['service']}:{series['metric']}:{scope}",
                "kind": "metric_series",
            }
        )

    # Every document must carry `service` even where it has none. The container is partitioned by
    # /kind then /service, and Cosmos distinguishes an ABSENT second level from a null one: a
    # document omitting the field is rejected outright ("PartitionKey extracted from document
    # doesn't match the one specified in the header"), while an explicit null is accepted and lands
    # under the undefined level. Verified against the live container, both branches.
    for document in out:
        document.setdefault("service", None)

    out.sort(key=lambda d: (d["kind"], d["service"] or "", d["id"]))
    return out


def embed_all(texts: list[str], deployment: str, dimensions: int) -> list[list[float]]:
    """Embed passages through the Azure OpenAI deployment, keyless via managed identity.

    Imported lazily so that `--dry-run` and every deterministic test can shape documents without
    the optional `openai` package or any Azure credential.
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AzureOpenAI

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from opspilot import config

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    client = AzureOpenAI(
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        api_version=config.AZURE_OPENAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )

    vectors: list[list[float]] = []
    for batch in _batched(texts, 64):
        response = client.embeddings.create(model=deployment, input=list(batch))
        vectors.extend(item.embedding for item in response.data)
    if any(len(v) != dimensions for v in vectors):
        raise SystemExit(
            f"embedding deployment returned a dimension other than {dimensions}; the container's "
            "vector policy fixes this, so they must agree"
        )
    return vectors


def _batched(items: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def seed(documents: list[dict[str, Any]], database: str, container: str) -> int:
    """Upsert documents into a container. Upsert rather than create so a re-run converges rather
    than failing on the second pass, which is what makes the preparation idempotent.

    There is deliberately no retry here. Writing ~14,000 documents one at a time will occasionally
    meet a dropped connection, and it did: a run on 2026-08-10 died partway through with
    `RemoteDisconnected`. Idempotence is the answer to that rather than retry machinery. Re-running
    after a partial run left both containers byte-identical to a fresh shaping, verified by
    comparing every live passage's id, text, identifiers, and category against local output. Adding
    a retry loop here would be machinery the accepted design does not ask for, to solve a problem
    re-running already solves.
    """
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from opspilot import config

    client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    target = client.get_database_client(database).get_container_client(container)
    for document in documents:
        target.upsert_item(document)
    return len(documents)


def verify(expected_knowledge: int, expected_operational: int) -> int:
    """Read back what preparation wrote and check the properties 1.3 names.

    Azure-assisted and never a CI gate: it needs the live containers. The document-shaping half of
    the same properties is asserted deterministically in `tests/test_corpus_preparation.py`; this
    is the half that can only be answered by the store.
    """
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from opspilot import config

    client = CosmosClient(config.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    database = client.get_database_client(config.COSMOS_RETAILEASE_DATABASE)
    knowledge = database.get_container_client(config.COSMOS_KNOWLEDGE_CONTAINER)
    operational = database.get_container_client(config.COSMOS_OPERATIONAL_RECORDS_CONTAINER)

    def count(container, where: str = "") -> int:
        query = f"SELECT VALUE COUNT(1) FROM c {where}".strip()
        return list(container.query_items(query, enable_cross_partition_query=True))[0]

    failures: list[str] = []

    got_knowledge = count(knowledge)
    got_operational = count(operational)
    if got_knowledge != expected_knowledge:
        failures.append(f"knowledge: expected {expected_knowledge}, read back {got_knowledge}")
    if got_operational != expected_operational:
        failures.append(
            f"operational-records: expected {expected_operational}, read back {got_operational}"
        )

    uncategorized = count(knowledge, "WHERE NOT IS_DEFINED(c.category) OR c.category = null")
    if uncategorized:
        failures.append(f"{uncategorized} knowledge documents carry no collection category")

    unembedded = count(knowledge, "WHERE NOT IS_DEFINED(c.embedding)")
    if unembedded:
        failures.append(f"{unembedded} knowledge documents carry no embedding")

    without_identifiers = count(knowledge, "WHERE ARRAY_LENGTH(c.identifiers) = 0")
    print(f"  knowledge without identifiers: {without_identifiers} (expected: some, not all)")
    if without_identifiers == got_knowledge:
        failures.append("no knowledge document carries an extracted identifier")

    dated = count(knowledge, "WHERE IS_DEFINED(c.date) AND c.date != null")
    if not dated:
        failures.append("no knowledge document carries time metadata")

    for kind in ("incident", "alert", "deployment", "dependency", "log", "metric_series"):
        if not count(operational, f"WHERE c.kind = '{kind}'"):
            failures.append(f"operational-records holds no {kind} records")

    print(f"  knowledge={got_knowledge} operational-records={got_operational} dated={dated}")
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  read-back verification passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="shape and report documents without embedding or writing anything",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="read back the containers and check them, without embedding or writing",
    )
    args = parser.parse_args(argv)

    knowledge = knowledge_documents()
    operational = operational_documents()

    categories = sorted({d["category"] for d in knowledge})
    kinds = sorted({d["kind"] for d in operational})
    with_identifiers = sum(1 for d in knowledge if d["identifiers"])
    with_dates = sum(1 for d in knowledge if d["date"])

    print(f"knowledge passages: {len(knowledge)} across categories {categories}")
    print(f"  carrying identifiers: {with_identifiers} | carrying a date: {with_dates}")
    print(f"operational records: {len(operational)} across kinds {kinds}")

    if args.dry_run:
        print("dry run: nothing embedded, nothing written")
        return 0

    if args.verify_only:
        print("read-back verification:")
        return verify(len(knowledge), len(operational))

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from opspilot import config

    vectors = embed_all(
        [d["text"] for d in knowledge], config.EMBEDDING_DEPLOYMENT, config.EMBEDDING_DIMENSIONS
    )
    for document, vector in zip(knowledge, vectors, strict=True):
        document["embedding"] = vector

    wrote_knowledge = seed(
        knowledge, config.COSMOS_RETAILEASE_DATABASE, config.COSMOS_KNOWLEDGE_CONTAINER
    )
    wrote_operational = seed(
        operational,
        config.COSMOS_RETAILEASE_DATABASE,
        config.COSMOS_OPERATIONAL_RECORDS_CONTAINER,
    )
    print(f"seeded knowledge={wrote_knowledge} operational-records={wrote_operational}")
    print("read-back verification:")
    return verify(wrote_knowledge, wrote_operational)


if __name__ == "__main__":
    raise SystemExit(main())
