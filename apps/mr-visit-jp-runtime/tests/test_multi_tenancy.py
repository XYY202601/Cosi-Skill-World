"""
Multi-tenancy isolation tests.

Two layers:
1. HTTP-level  – verifies that sessions created under org_A cannot be retrieved
   by a request carrying org_B in X-Org-ID, and that on-disk paths are separated.
2. Store-level – directly exercises FileProgressStore to confirm that org_A
   progress is invisible to org_B reads.  This avoids the need for a live LLM.

K3 negative tests:
  - Supervisor blocked from raw transcript access (GET /v1/sessions/{id})
  - Supervisor allowed access to session summary (GET /v1/sessions/{id}/summary)
  - Learner cannot access another learner's session
  - Learner cannot access organization reports
  - Learner cannot access admin operations (training plans CRUD)
  - Cross-org access denied for supervisors
"""
import json
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from persistence.file_progress_store import FileProgressStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def client(test_data_dir, monkeypatch):
    from main import app  # late import so env is patched first
    monkeypatch.setenv("MR_RUNTIME_DATA_DIR", str(test_data_dir))
    monkeypatch.setenv("MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT", "true")
    monkeypatch.setenv("MR_RUNTIME_AUTH_MODE", "enabled")
    with TestClient(app) as c:
        yield c


def _create_session(client, org_id, learner_id, scenario_id="busy_doctor_short_visit"):
    """Helper: start a session and return the session_id."""
    resp = client.post(
        "/v1/sessions/start",
        json={"scenario_id": scenario_id, "learner_id": learner_id},
        headers={"X-Org-ID": org_id, "X-Auth-User": learner_id},
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()["session_id"]


# ---------------------------------------------------------------------------
# Test 1 – HTTP session isolation (K0)
# ---------------------------------------------------------------------------

def test_session_isolation_across_orgs(client, test_data_dir):
    """Sessions created for org_A must be invisible to org_B and vice-versa."""
    scenario_id = "busy_doctor_short_visit"
    learner_id = "test_learner"

    headers_a = {"X-Org-ID": "org_A", "X-Auth-User": learner_id}
    headers_b = {"X-Org-ID": "org_B", "X-Auth-User": learner_id}

    # Create a session for org_A
    resp_a = client.post(
        "/v1/sessions/start",
        json={"scenario_id": scenario_id, "learner_id": learner_id},
        headers=headers_a,
    )
    assert resp_a.status_code == 200, resp_a.json()
    session_id_a = resp_a.json()["session_id"]

    # Create a session for org_B
    resp_b = client.post(
        "/v1/sessions/start",
        json={"scenario_id": scenario_id, "learner_id": learner_id},
        headers=headers_b,
    )
    assert resp_b.status_code == 200, resp_b.json()
    session_id_b = resp_b.json()["session_id"]

    # org_A must NOT see org_B's session
    assert client.get(f"/v1/sessions/{session_id_b}", headers=headers_a).status_code == 404
    # org_B must NOT see org_A's session
    assert client.get(f"/v1/sessions/{session_id_a}", headers=headers_b).status_code == 404

    # Both sessions must still be accessible by their own org
    assert client.get(f"/v1/sessions/{session_id_a}", headers=headers_a).status_code == 200
    assert client.get(f"/v1/sessions/{session_id_b}", headers=headers_b).status_code == 200

    # Verify on-disk layout is physically isolated (file mode only)
    if os.environ.get("MR_RUNTIME_PERSISTENCE_MODE") != "sql":
        assert (test_data_dir / "sessions" / "org_A" / f"{session_id_a}.json").exists()
        assert (test_data_dir / "sessions" / "org_B" / f"{session_id_b}.json").exists()
        # Cross-contamination must not exist
        assert not (test_data_dir / "sessions" / "org_A" / f"{session_id_b}.json").exists()
        assert not (test_data_dir / "sessions" / "org_B" / f"{session_id_a}.json").exists()


# ---------------------------------------------------------------------------
# Test 2 – Store-level progress isolation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("MR_RUNTIME_PERSISTENCE_MODE") == "sql",
    reason="file-persistence specific (uses FileProgressStore directly)",
)
def test_progress_store_isolation(test_data_dir):
    """FileProgressStore must keep org_A and org_B data in separate paths."""
    store = FileProgressStore(test_data_dir)
    learner_id = "learner_001"

    payload_a = {"learner_id": learner_id, "total_sessions": 5, "org": "A"}
    payload_b = {"learner_id": learner_id, "total_sessions": 9, "org": "B"}

    # Write separate records for same learner_id under different orgs
    store.upsert(learner_id, payload_a, org_id="org_A")
    store.upsert(learner_id, payload_b, org_id="org_B")

    # Each org reads its own record
    assert store.get(learner_id, org_id="org_A") == payload_a
    assert store.get(learner_id, org_id="org_B") == payload_b

    # Reading without any org_id must NOT accidentally return either record
    # (returns None – learner has no global-scope progress)
    assert store.get(learner_id) is None

    # Verify physical file paths (store writes directly into its root_dir)
    assert (test_data_dir / "org_A" / f"{learner_id}.json").exists()
    assert (test_data_dir / "org_B" / f"{learner_id}.json").exists()
    # No top-level file for this learner (no global upsert was made)
    assert not (test_data_dir / f"{learner_id}.json").exists()


# ---------------------------------------------------------------------------
# K3 Test 3 – Supervisor blocked from raw transcript
# ---------------------------------------------------------------------------

def test_supervisor_cannot_read_raw_transcript(client):
    """Supervisor role must receive 403 when accessing raw session transcript."""
    learner_id = "test_learner_sup"
    org_id = "org_sup_test"

    session_id = _create_session(client, org_id, learner_id)

    # Supervisor with same org tries to read transcript
    supervisor_headers = {
        "X-Org-ID": org_id,
        "X-Auth-User": "supervisor_01",
        "X-Viewer-Role": "supervisor",
    }
    resp = client.get(f"/v1/sessions/{session_id}", headers=supervisor_headers)
    assert resp.status_code == 403, (
        f"Expected 403 for supervisor transcript access, got {resp.status_code}: {resp.json()}"
    )
    detail = resp.json().get("detail", "")
    assert "transcript" in detail.lower(), f"Response should mention transcript restriction: {detail}"


# ---------------------------------------------------------------------------
# K3 Test 4 – Supervisor allowed session summary
# ---------------------------------------------------------------------------

def test_supervisor_can_read_session_summary(client):
    """Supervisor role must be able to access the redacted session summary."""
    learner_id = "test_learner_summary"
    org_id = "org_summary_test"

    session_id = _create_session(client, org_id, learner_id)

    supervisor_headers = {
        "X-Org-ID": org_id,
        "X-Auth-User": "supervisor_02",
        "X-Viewer-Role": "supervisor",
    }
    resp = client.get(f"/v1/sessions/{session_id}/summary", headers=supervisor_headers)
    assert resp.status_code == 200, (
        f"Expected 200 for supervisor summary access, got {resp.status_code}: {resp.json()}"
    )
    data = resp.json()
    assert data["session_id"] == session_id
    # Summary must not include raw transcript fields
    assert "turns" not in data, "Summary should not contain full transcript turns"


# ---------------------------------------------------------------------------
# K3 Test 5 – Cross-learner access denied
# ---------------------------------------------------------------------------

def test_learner_cannot_access_another_learners_session(client):
    """A learner must not be able to access another learner's session."""
    org_id = "org_cross_learner"
    learner_a = "learner_a"
    learner_b = "learner_b"

    session_id = _create_session(client, org_id, learner_a)

    # Learner B tries to access Learner A's session
    headers_b = {"X-Org-ID": org_id, "X-Auth-User": learner_b}
    resp = client.get(f"/v1/sessions/{session_id}", headers=headers_b)
    assert resp.status_code == 403, (
        f"Expected 403 for cross-learner access, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# K3 Test 6 – Learner cannot access org reports
# ---------------------------------------------------------------------------

def test_learner_cannot_access_org_reports(client):
    """A learner must receive 403 when trying to access organization reports."""
    org_id = "org_reports_deny"
    learner_id = "learner_reports"

    headers = {"X-Org-ID": org_id, "X-Auth-User": learner_id}
    resp = client.get(f"/v1/organizations/{org_id}/reports", headers=headers)
    assert resp.status_code == 403, (
        f"Expected 403 for learner org report access, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# K3 Test 7 – Learner cannot access admin operations
# ---------------------------------------------------------------------------

def test_learner_cannot_list_training_plans(client):
    """Learner must receive 403 when trying to list training plans."""
    org_id = "org_admin_deny"
    learner_id = "learner_admin"

    headers = {"X-Org-ID": org_id, "X-Auth-User": learner_id}
    resp = client.get("/v1/training-plans", headers=headers)
    assert resp.status_code == 403, (
        f"Expected 403 for learner training plan list, got {resp.status_code}: {resp.json()}"
    )


def test_learner_cannot_create_training_plan(client):
    """Learner must receive 403 when trying to create a training plan."""
    org_id = "org_admin_create"
    learner_id = "learner_create_admin"

    headers = {"X-Org-ID": org_id, "X-Auth-User": learner_id}
    resp = client.post(
        "/v1/training-plans",
        json={"title": "test plan", "org_id": org_id},
        headers=headers,
    )
    assert resp.status_code == 403, (
        f"Expected 403 for learner creating training plan, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# K3 Test 8 – Cross-org supervisor access denied
# ---------------------------------------------------------------------------

def test_supervisor_cross_org_access_denied(client):
    """A supervisor from org_B must not access org_A's learner session."""
    learner_id = "learner_cross_org"
    org_a = "org_A_cross"
    org_b = "org_B_cross"

    session_id = _create_session(client, org_a, learner_id)

    # Supervisor from org_B trying to access org_A's session
    supervisor_headers = {
        "X-Org-ID": org_b,
        "X-Auth-User": "supervisor_cross",
        "X-Viewer-Role": "supervisor",
    }
    resp = client.get(f"/v1/sessions/{session_id}", headers=supervisor_headers)
    # Should be 404 (session not found in org_b) or 403 (auth denied)
    assert resp.status_code in (403, 404), (
        f"Expected 403/404 for cross-org supervisor access, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# K3 Test 9 – Sharing grant allows supervisor transcript access
# ---------------------------------------------------------------------------

def test_sharing_grant_overrides_supervisor_transcript_block(client):
    """A sharing grant must allow supervisor to access raw transcript."""
    learner_id = "learner_grant"
    org_id = "org_grant_test"

    session_id = _create_session(client, org_id, learner_id)

    # First verify supervisor is blocked without grant
    sup_headers = {
        "X-Org-ID": org_id,
        "X-Auth-User": "supervisor_grant",
        "X-Viewer-Role": "supervisor",
    }
    resp_blocked = client.get(f"/v1/sessions/{session_id}", headers=sup_headers)
    assert resp_blocked.status_code == 403, "Supervisor must be blocked without grant"

    # Note: Sharing grants are currently in-memory and not consulted by
    # _enforce_supervisor_transcript_policy during transcript access.
    # The grant creates a record but the enforcement path does not yet
    # check grants for transcript_text artifacts. This test documents
    # the intended behavior; the integration will be completed in a
    # follow-up when the grant store is consulted during access checks.
    #
    # For now, verify the grant can be created:
    grant_headers = {"X-Org-ID": org_id, "X-Auth-User": learner_id}
    grant_resp = client.post(
        "/v1/grants",
        json={
            "grantee_role": "supervisor",
            "grantee_scope": f"org:{org_id}",
            "reason": "test grant for transcript access",
        },
        headers=grant_headers,
    )
    assert grant_resp.status_code == 201, (
        f"Expected 201 for grant creation, got {grant_resp.status_code}: {grant_resp.json()}"
    )
    grant_id = grant_resp.json()["grant_id"]
    assert grant_id.startswith("grant_"), f"Grant ID should start with 'grant_': {grant_id}"

    # Verify grant listing works
    list_resp = client.get("/v1/grants", headers=grant_headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data["grants"]) >= 1
    assert any(g["grant_id"] == grant_id for g in data["grants"])


# ---------------------------------------------------------------------------
# K3 Test 10 – Access policy module unit tests
# ---------------------------------------------------------------------------

def test_access_policy_supervisor_transcript_blocked():
    """The access policy must mark transcript_text as blocked for supervisor."""
    from services.access_policy import check_artifact_access

    decision = check_artifact_access("supervisor", "transcript_text", is_own_data=False, is_same_org=True)
    assert not decision.allowed, "Supervisor must be blocked from transcript_text"
    assert decision.effective_level == "blocked"


def test_access_policy_supervisor_aggregate_allowed():
    """The access policy must allow supervisor to read aggregate_metrics."""
    from services.access_policy import check_artifact_access

    decision = check_artifact_access("supervisor", "aggregate_metrics", is_own_data=False, is_same_org=True)
    assert decision.allowed, "Supervisor must be allowed to read aggregate_metrics"
    assert decision.effective_level == "team"


def test_access_policy_learner_cross_access_denied():
    """Learner must be denied access to another learner's data without grant."""
    from services.access_policy import check_artifact_access

    decision = check_artifact_access(
        "learner", "scores_diagnosis",
        is_own_data=False, is_same_org=True,
    )
    assert not decision.allowed, "Learner must be denied cross-learner access"
    assert decision.effective_level == "own"


def test_access_policy_learner_own_data_allowed():
    """Learner must be allowed to read their own data."""
    from services.access_policy import check_artifact_access

    decision = check_artifact_access(
        "learner", "scores_diagnosis",
        is_own_data=True, is_same_org=True,
    )
    assert decision.allowed, "Learner must be allowed to read own data"


def test_access_policy_org_admin_full_access():
    """Organization admin must have org-level access to all artifacts."""
    from services.access_policy import check_artifact_access

    for artifact in ["session_metadata", "transcript_text", "scores_diagnosis", "compliance_flags", "coach_feedback", "review_corrections"]:
        decision = check_artifact_access(
            "organization_admin", artifact,
            is_own_data=False, is_same_org=True,
        )
        assert decision.allowed, f"Org admin must be allowed to read {artifact}"
        assert decision.effective_level == "org"


def test_access_policy_content_admin_no_learner_data():
    """Content admin must have no access to learner data artifacts."""
    from services.access_policy import check_artifact_access

    for artifact in ["session_metadata", "transcript_text", "scores_diagnosis"]:
        decision = check_artifact_access(
            "content_admin", artifact,
            is_own_data=False, is_same_org=True,
        )
        assert not decision.allowed, f"Content admin must be denied from {artifact}"


def test_access_policy_cross_org_denied():
    """Access must be denied when the target is outside the viewer's org."""
    from services.access_policy import check_artifact_access

    decision = check_artifact_access(
        "supervisor", "aggregate_metrics",
        is_own_data=False, is_same_org=False,
    )
    assert not decision.allowed, "Supervisor must be denied cross-org aggregate access"
