from __future__ import annotations
from typing import Any

def get_peer_benchmark(scenario_id: str) -> dict[str, Any]:
    """
    Returns a static peer benchmark for the given scenario.
    In a real system, this would come from a database of top performers.
    """
    # Sample high-performer profile
    return {
        "scenario_id": scenario_id,
        "peer_average_score": 88,
        "peer_top_score": 96,
        "subskill_benchmarks": {
            "preparation": 4.5,
            "opening": 4.8,
            "profiling": 4.2,
            "scientific_delivery": 4.6,
            "need_discovery": 4.4,
            "objection_handling": 4.0,
            "closing_followup": 4.7
        },
        "target_band": "excellent"
    }
