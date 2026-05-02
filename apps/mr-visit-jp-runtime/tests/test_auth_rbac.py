import pytest
from fastapi.testclient import TestClient

from providers import clear_prompt_asset_cache
from scenarios.asset_loader import get_domain_bundle


SCENARIO_ID = "busy_doctor_short_visit"
ORG_ID = "org_auth"


@pytest.fixture(autouse=True)
def clear_asset_caches():
    get_domain_bundle.cache_clear()
    clear_prompt_asset_cache()
    yield
    get_domain_bundle.cache_clear()
    clear_prompt_asset_cache()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MR_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))
    monkeypatch.setenv("MR_RUNTIME_AUTH_MODE", "enabled")
    monkeypatch.setenv("MR_RUNTIME_MODEL_MODE", "mock")
    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", "manual")
    monkeypatch.setenv("MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT", "true")
    from main import app

    with TestClient(app) as runtime_client:
        yield runtime_client


def auth_headers(user_id: str, role: str = "learner", org_id: str = ORG_ID) -> dict[str, str]:
    return {
        "X-Auth-User": user_id,
        "X-Org-ID": org_id,
        "X-Viewer-Role": role,
    }


def start_session(client: TestClient, learner_id: str, headers: dict[str, str]) -> str:
    response = client.post(
        "/v1/sessions/start",
        json={"scenario_id": SCENARIO_ID, "learner_id": learner_id},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return str(response.json()["session_id"])


def finish_session(client: TestClient, session_id: str, headers: dict[str, str]) -> None:
    turn = client.post(
        f"/v1/sessions/{session_id}/turn",
        json={"message": "Use one clear evidence point for this physician."},
        headers=headers,
    )
    assert turn.status_code == 200, turn.json()
    finished = client.post(f"/v1/sessions/{session_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.json()


def test_auth_enabled_requires_identity_on_protected_routes(client):
    public_response = client.get("/v1/scenarios")
    assert public_response.status_code == 200

    protected_response = client.get("/v1/learners/learner_a/progress")
    assert protected_response.status_code == 401
    assert "Authentication required" in protected_response.json()["detail"]


def test_auth_enabled_rejects_missing_org_context(client):
    response = client.get(
        "/v1/learners/learner_a/progress",
        headers={"X-Auth-User": "learner_a"},
    )
    assert response.status_code == 401
    assert "Organization context required" in response.json()["detail"]


def test_learner_cannot_start_or_read_another_learners_session(client):
    learner_a_headers = auth_headers("learner_a")
    learner_b_headers = auth_headers("learner_b")

    forbidden_start = client.post(
        "/v1/sessions/start",
        json={"scenario_id": SCENARIO_ID, "learner_id": "learner_b"},
        headers=learner_a_headers,
    )
    assert forbidden_start.status_code == 403

    session_id = start_session(client, "learner_b", learner_b_headers)

    forbidden_session = client.get(
        f"/v1/sessions/{session_id}",
        headers=learner_a_headers,
    )
    assert forbidden_session.status_code == 403
    assert "own training data" in forbidden_session.json()["detail"]

    own_session = client.get(f"/v1/sessions/{session_id}", headers=learner_b_headers)
    assert own_session.status_code == 200, own_session.json()


def test_supervisor_can_view_permitted_drilldown_but_not_transcripts(client):
    learner_headers = auth_headers("learner_b")
    supervisor_headers = auth_headers("supervisor_1", role="supervisor")
    session_id = start_session(client, "learner_b", learner_headers)
    finish_session(client, session_id, learner_headers)

    review = client.get(f"/v1/sessions/{session_id}/review", headers=supervisor_headers)
    assert review.status_code == 200, review.json()
    assert review.json()["learner_id"] == "learner_b"

    progress = client.get("/v1/learners/learner_b/progress", headers=supervisor_headers)
    assert progress.status_code == 200, progress.json()

    transcript = client.get(f"/v1/sessions/{session_id}", headers=supervisor_headers)
    assert transcript.status_code == 403
    assert "raw session transcripts" in transcript.json()["detail"]


def test_supervisor_transcript_view_fallback_contract_returns_redacted_summary(client):
    learner_headers = auth_headers("learner_c")
    supervisor_headers = auth_headers("supervisor_2", role="supervisor")
    session_id = start_session(client, "learner_c", learner_headers)
    finish_session(client, session_id, learner_headers)

    transcript = client.get(f"/v1/sessions/{session_id}", headers=supervisor_headers)
    assert transcript.status_code == 403
    assert "raw session transcripts" in transcript.json()["detail"]

    summary = client.get(f"/v1/sessions/{session_id}/summary", headers=supervisor_headers)
    assert summary.status_code == 200, summary.json()
    payload = summary.json()
    assert payload["session_id"] == session_id
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["status"] in {"active", "awaiting_finish", "finalized"}
    assert isinstance(payload["turn_count"], int)
    assert payload["turn_count"] >= 1
    assert isinstance(payload["review_ready"], bool)
    assert payload["review_ready"] is True
    assert "turns" not in payload


def test_supervisor_can_read_own_session_transcript(client):
    supervisor_headers = auth_headers("supervisor_self", role="supervisor")
    session_id = start_session(client, "supervisor_self", supervisor_headers)

    session = client.get(f"/v1/sessions/{session_id}", headers=supervisor_headers)
    assert session.status_code == 200, session.json()
    assert session.json()["learner_id"] == "supervisor_self"

    events = client.get(f"/v1/sessions/{session_id}/events", headers=supervisor_headers)
    assert events.status_code == 200, events.json()
    assert events.json()["session_id"] == session_id


def test_reports_and_admin_gates_require_roles(client):
    learner_headers = auth_headers("learner_a")
    supervisor_headers = auth_headers("supervisor_1", role="supervisor")
    content_admin_headers = auth_headers("content_admin_1", role="content_admin")

    learner_reports = client.get(
        f"/v1/organizations/{ORG_ID}/reports",
        headers=learner_headers,
    )
    assert learner_reports.status_code == 403

    supervisor_reports = client.get(
        f"/v1/organizations/{ORG_ID}/reports",
        headers=supervisor_headers,
    )
    assert supervisor_reports.status_code == 200, supervisor_reports.json()

    learner_gates = client.get("/v1/evaluation-gates", headers=learner_headers)
    assert learner_gates.status_code == 403

    admin_gates = client.get("/v1/evaluation-gates", headers=content_admin_headers)
    assert admin_gates.status_code == 200, admin_gates.json()
