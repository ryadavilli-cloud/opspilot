"""Corpus preparation: the properties 1.3 verifies by reading back what it wrote.

These run against the shaped documents rather than a live container, so they are deterministic and
belong in CI. The live read-back after seeding is an Azure-assisted check and is never a CI gate.

The preparation script is imported by path because nothing in the runtime may import it: it is an
offline setup task, not a component. Same pattern the answer key's `build_goldens.py` already uses.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = _load("prepare_corpus", "scripts/prepare_corpus.py")

KNOWLEDGE = prep.knowledge_documents()
OPERATIONAL = prep.operational_documents()
SCENARIOS = yaml.safe_load(
    (REPO_ROOT / "data" / "answer_key" / "scenarios.yaml").read_text(encoding="utf-8")
)["scenarios"]
GOLDEN = yaml.safe_load(
    (REPO_ROOT / "data" / "answer_key" / "golden_scenarios.yaml").read_text(encoding="utf-8")
)["golden_scenarios"]


# --- chunking (D-003: one passage per section, no overlap; short documents stay whole) ---------
def test_every_passage_belongs_to_exactly_one_document_section():
    # No overlap means no passage text appears under two ids. A duplicated id would also silently
    # collapse documents on upsert.
    ids = [doc["id"] for doc in KNOWLEDGE]
    assert len(ids) == len(set(ids)), "duplicate passage id would overwrite on upsert"
    for doc in KNOWLEDGE:
        assert doc["chunk_id"].startswith(f"{doc['doc_id']}#")
        assert doc["id"] == prep.cosmos_id(doc["chunk_id"])


def test_document_ids_contain_no_character_cosmos_rejects():
    # Cosmos rejects '/', '\\', '?', and '#' in an id, and rejects the whole write rather than
    # sanitizing. The chunker's own separator is '#', so this is not hypothetical.
    illegal = set("/\\?#")
    for doc in KNOWLEDGE + OPERATIONAL:
        assert not (illegal & set(doc["id"])), f"{doc['id']!r} contains a character Cosmos rejects"


def test_the_id_translation_is_reversible_and_collision_free():
    # A many-to-one translation would merge two passages into one document on upsert.
    translated = {prep.cosmos_id(doc["chunk_id"]): doc["chunk_id"] for doc in KNOWLEDGE}
    assert len(translated) == len(KNOWLEDGE), "the id translation collapsed two distinct passages"


def test_a_document_with_no_headers_stays_whole():
    doc = prep.chunk(
        prep.load_docs.__globals__["Doc"](
            doc_id="runbook:flat",
            kind="runbook",
            title="Flat",
            services=("checkout-api",),
            text="No headings here, just prose.",
            is_distractor=False,
        )
    )
    assert len(doc) == 1, "a header-less document must not be split"


# --- metadata contract ------------------------------------------------------------------------
def test_every_knowledge_document_carries_a_known_collection_category():
    assert KNOWLEDGE, "no knowledge passages were produced"
    for doc in KNOWLEDGE:
        assert doc["category"] in prep.KNOWN_CATEGORIES, (
            f"{doc['id']} has category {doc['category']!r}, which is not one of the three "
            "routed logical collections"
        )


def test_every_knowledge_document_carries_provenance():
    for doc in KNOWLEDGE:
        assert doc["provenance"]["source"] in ("data/kb", "data/distractors")
        assert doc["provenance"]["doc_id"] == doc["doc_id"]


def test_time_metadata_is_present_where_it_exists_and_absent_where_it_does_not():
    # Postmortems inherit their incident's date. Runbooks and architecture docs have none, and a
    # fabricated one would skew any time-window promotion, so absence must survive preparation.
    dated = {d["doc_id"] for d in KNOWLEDGE if d["date"] is not None}
    assert dated, "no passage carries a date, so time metadata was dropped entirely"
    assert all(doc_id.startswith("postmortem:") for doc_id in dated)

    real_postmortems = {f"postmortem:{s['id']}" for s in SCENARIOS if s["type"] != "novel"}
    assert real_postmortems & dated, "authored postmortems must carry their incident's date"

    for doc in KNOWLEDGE:
        if doc["category"] in ("runbook", "architecture"):
            assert doc["date"] is None, f"{doc['id']} invented a date it has no source for"


def test_entity_metadata_survives_as_a_list():
    # Retrieval filters by service, and `services` is a list in frontmatter, which is why it is
    # entity metadata rather than the partition key.
    assert any(doc["services"] for doc in KNOWLEDGE)
    for doc in KNOWLEDGE:
        assert isinstance(doc["services"], list)


# --- identifier extraction (D-003) ------------------------------------------------------------
def test_identifiers_are_extracted_for_services_error_codes_and_deploy_ids():
    every = {ident for doc in KNOWLEDGE for ident in doc["identifiers"]}
    entities = set(prep.topology_entities())
    assert every & entities, "no service name was extracted"
    assert {i for i in every if i.startswith("dep-")}, "no deployment identifier was extracted"
    assert {i for i in every if i in ("429", "500", "503", "5xx")}, "no error code was extracted"


def test_identifiers_the_golden_records_designate_are_extractable():
    # The property that matters: an identifier a golden record names as required evidence must be
    # findable in the prepared corpus. One that is not is a preparation gap, not a test to relax.
    designated: set[str] = set()
    for record in GOLDEN:
        for group in record["required_evidence"]:
            for ref in group.get("any_of", []) + group.get("all_of", []):
                if ref.startswith("deploys:"):
                    designated.add(ref.rsplit(":", 1)[1])
    assert designated, "no golden record designates a deployment identifier"

    extracted = {i for doc in KNOWLEDGE for i in doc["identifiers"] if i.startswith("dep-")}
    # Not every designated deploy id is discussed in prose, but the ones that are must extract.
    assert designated & extracted, (
        "no golden-record deployment identifier survives extraction, so exact-identifier "
        "matching cannot promote the passage that mentions it"
    )


def test_extraction_is_stable_across_runs():
    # A re-run must produce the same identifiers, which is half of 1.3's idempotence claim.
    again = prep.knowledge_documents()
    assert [d["identifiers"] for d in again] == [d["identifiers"] for d in KNOWLEDGE]
    assert [d["id"] for d in again] == [d["id"] for d in KNOWLEDGE]


# --- distractors ------------------------------------------------------------------------------
def test_distractors_are_loaded_and_indistinguishable_by_category():
    # Precision is only measurable if the container holds retrievable-but-wrong passages. A
    # distractor that were excluded, or that carried a category retrieval could filter on, would
    # make every retrieved passage correct by construction.
    sources = {doc["provenance"]["source"] for doc in KNOWLEDGE}
    assert "data/distractors" in sources, "distractors were not loaded"

    distractor_categories = {
        doc["category"] for doc in KNOWLEDGE if doc["provenance"]["source"] == "data/distractors"
    }
    real_categories = {
        doc["category"] for doc in KNOWLEDGE if doc["provenance"]["source"] == "data/kb"
    }
    assert distractor_categories <= real_categories, (
        "distractors occupy a category real knowledge does not, which would let retrieval "
        "filter them out and defeat precision measurement"
    )


# --- operational records ----------------------------------------------------------------------
def test_every_operational_record_carries_its_partition_kind():
    expected = {"incident", "alert", "deployment", "dependency", "log", "metric_series"}
    assert {doc["kind"] for doc in OPERATIONAL} == expected


def test_service_keyed_records_carry_the_second_partition_level():
    # Logs, metrics, deployments, and alerts are queried by service, so the second partition level
    # must be populated for them or those queries fan out across the whole kind.
    for kind in ("log", "metric_series", "deployment", "alert"):
        records = [d for d in OPERATIONAL if d["kind"] == kind]
        assert records, f"no {kind} records were produced"
        assert all(d.get("service") for d in records), f"{kind} records missing `service`"


def test_every_operational_record_carries_the_service_key_even_when_it_has_none():
    # Cosmos distinguishes an absent second partition level from a null one. Omitting `service`
    # is rejected at write time; an explicit null is accepted and lands under the undefined level.
    # Incidents and dependency edges genuinely have no service, so they must carry null, not gaps.
    for doc in OPERATIONAL:
        assert "service" in doc, f"{doc['kind']}:{doc['id']} omits the second partition level"

    service_less = {doc["kind"] for doc in OPERATIONAL if doc["service"] is None}
    assert service_less == {"incident", "dependency"}, (
        f"unexpected kinds carry no service: {service_less}"
    )


def test_operational_record_ids_are_unique():
    ids = [(doc["kind"], doc["id"]) for doc in OPERATIONAL]
    assert len(ids) == len(set(ids)), "duplicate (kind, id) would overwrite on upsert"


def test_a_record_field_colliding_with_a_partition_path_is_relocated_not_overwritten():
    """A dependency edge names its own relationship kind, and `kind` is also the container's first
    partition level. Spreading the edge and then setting the partition value overwrites the
    relationship with the literal "dependency", and nothing fails at write time: the read side
    simply finds every edge claiming the same kind. This is the only kind whose own field collides
    with a partition path, so it is the only one relocated.
    """
    source = {
        (edge["from"], edge["to"]): edge["kind"] for edge in prep._records("dependencies", "edges")
    }
    prepared = [doc for doc in OPERATIONAL if doc["kind"] == "dependency"]

    assert len(prepared) == len(source)
    for doc in prepared:
        assert doc["dependency_kind"] == source[(doc["from"], doc["to"])]
    assert len({doc["dependency_kind"] for doc in prepared}) > 1, (
        "every edge reporting one relationship kind is what the collision looked like"
    )


@pytest.mark.parametrize(
    "name,key,kind,id_field",
    [
        ("incidents", "incidents", "incident", "incident_id"),
        # Alerts carry BOTH alert_id and incident_id; the record's own identity is alert_id.
        ("alerts", "alerts", "alert", "alert_id"),
        ("deployments", "deployments", "deployment", "deploy_id"),
    ],
)
def test_operational_records_preserve_their_source_fields(
    name: str, key: str, kind: str, id_field: str
):
    # Preparation relocates records; it must not reshape them, or the tools that read them back
    # would need a second contract.
    source = prep._records(name, key)
    prepared = {d["id"]: d for d in OPERATIONAL if d["kind"] == kind}
    assert len(prepared) == len(source)
    for record in source:
        got = prepared[record[id_field]]
        for field, value in record.items():
            assert got[field] == value, f"{field} changed during preparation"
