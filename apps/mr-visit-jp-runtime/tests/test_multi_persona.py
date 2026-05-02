import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_multi_persona_turn():
    # Start a session
    resp = client.post("/v1/sessions/start", json={
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": "test_learner"
    })
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    
    # Send a turn with a specific persona (if it exists in the bundle)
    # Let's check which personas are available
    bundle = app.state.domain_bundle
    persona_ids = list(bundle.personas.keys())
    target_persona = persona_ids[0]
    
    resp = client.post(f"/v1/sessions/{session_id}/turn", json={
        "message": "Hello",
        "persona_id": target_persona
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["persona_id"] == target_persona
    
    # Get session and check turns
    resp = client.get(f"/v1/sessions/{session_id}")
    assert resp.status_code == 200
    turns = resp.json()["turns"]
    assert turns[-1]["persona_id"] == target_persona

def test_invalid_persona_id():
    resp = client.post("/v1/sessions/start", json={
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": "test_learner"
    })
    session_id = resp.json()["session_id"]
    
    resp = client.post(f"/v1/sessions/{session_id}/turn", json={
        "message": "Hello",
        "persona_id": "invalid_id"
    })
    assert resp.status_code == 404
