from __future__ import annotations

from pathlib import Path

from persistence.file_event_store import FileEventStore
from session_events import (
    SessionEventEnvelope,
    normalize_session_event_payload,
    normalize_session_event_payloads,
    sort_envelopes_for_replay,
)


REQUIRED_EVENT_FIELDS = (
    "type",
    "source",
    "stage",
    "content",
    "metadata",
    "skill_id",
    "session_id",
    "turn_id",
    "seq",
    "timestamp",
    "schema_version",
)


def test_session_event_envelope_requires_core_fields() -> None:
    event = SessionEventEnvelope(
        type="turn_processed",
        source="runtime",
        stage="practice_session",
        content={"message": "test"},
        metadata={"trace_id": "trace_001"},
        skill_id="mr_visit_jp",
        session_id="sess_001",
        turn_id="turn_001",
        seq=2,
        timestamp="2026-04-24T00:00:00Z",
        schema_version="1.0",
    )

    payload = event.to_dict()

    assert set(REQUIRED_EVENT_FIELDS).issubset(payload)


def test_session_event_envelope_sorts_by_seq_and_supports_replay() -> None:
    second = SessionEventEnvelope(
        type="turn_processed",
        source="runtime",
        stage="practice_session",
        content={"message": "second"},
        metadata={},
        skill_id="mr_visit_jp",
        session_id="sess_001",
        turn_id="turn_002",
        seq=2,
        timestamp="2026-04-24T00:00:02Z",
        schema_version="1.0",
    )
    first = SessionEventEnvelope(
        type="session_started",
        source="runtime",
        stage="practice_session",
        content={"message": "first"},
        metadata={},
        skill_id="mr_visit_jp",
        session_id="sess_001",
        turn_id="turn_001",
        seq=1,
        timestamp="2026-04-24T00:00:01Z",
        schema_version="1.0",
    )

    ordered = sort_envelopes_for_replay([second, first])

    assert [item.seq for item in ordered] == [1, 2]
    assert [item.type for item in ordered] == ["session_started", "turn_processed"]


def test_session_event_envelope_normalizes_legacy_payloads() -> None:
    payload = normalize_session_event_payload(
        {
            "type": "turn_processed",
            "session_id": "sess_001",
            "timestamp": "2026-04-24T00:00:02Z",
            "turn_index": 2,
            "director_phase": "discovery",
            "director_events": ["discovery_question_missing"],
            "recommended_action": "ask_one_targeted_discovery_question",
        },
        fallback_session_id="sess_001",
        inferred_seq=2,
    )

    assert payload["source"] == "runtime"
    assert payload["stage"] == "practice_session"
    assert payload["content"]["director_phase"] == "discovery"
    assert payload["turn_id"] == "sess_001:turn:0002"
    assert payload["seq"] == 2


def test_session_event_envelope_normalizes_and_orders_payload_lists() -> None:
    payloads = normalize_session_event_payloads(
        [
            {
                "type": "turn_processed",
                "session_id": "sess_001",
                "turn_index": 2,
                "timestamp": "2026-04-24T00:00:02Z",
            },
            {
                "type": "session_started",
                "session_id": "sess_001",
                "timestamp": "2026-04-24T00:00:01Z",
            },
        ],
        fallback_session_id="sess_001",
    )

    assert [item["seq"] for item in payloads] == [1, 2]
    assert [item["type"] for item in payloads] == ["session_started", "turn_processed"]


def test_file_event_store_reads_legacy_events_as_envelopes(tmp_path: Path) -> None:
    store = FileEventStore(tmp_path)
    store.replace(
        "sess_legacy",
        [
            {
                "type": "turn_processed",
                "session_id": "sess_legacy",
                "turn_index": 2,
                "timestamp": "2026-04-24T00:00:02Z",
            },
            {
                "type": "session_started",
                "session_id": "sess_legacy",
                "timestamp": "2026-04-24T00:00:01Z",
            },
        ],
    )

    events = store.list_events("sess_legacy")

    assert [item["seq"] for item in events] == [1, 2]
    assert [item["type"] for item in events] == ["session_started", "turn_processed"]
    assert events[1]["turn_id"] == "sess_legacy:turn:0002"
