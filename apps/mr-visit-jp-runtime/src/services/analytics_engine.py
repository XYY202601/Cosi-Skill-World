from __future__ import annotations
from typing import Any
from datetime import datetime

def derive_performance_trends(recent_history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Analyzes historical session data to identify performance trends.
    """
    if not recent_history:
        return {
            "overall_trend": "stable",
            "rolling_average": 0.0,
            "subskill_growth": {},
            "plateau_risk": False
        }

    # Extract overall scores
    scores = [
        int(item.get("overall_score", 0)) 
        for item in recent_history 
        if isinstance(item, dict) and "overall_score" in item
    ]
    
    if not scores:
        return {"overall_trend": "stable", "rolling_average": 0.0}

    # Calculate rolling average (last 5)
    recent_scores = scores[-5:]
    avg_score = sum(recent_scores) / len(recent_scores)
    
    # Simple trend detection
    if len(scores) >= 3:
        prev_avg = sum(scores[-6:-3]) / 3 if len(scores) >= 6 else scores[0]
        delta = avg_score - prev_avg
        if delta > 5:
            trend = "improving"
        elif delta < -5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Plateau risk: scores are stable (low delta) and below a target threshold (e.g., 75)
    plateau_risk = trend == "stable" and avg_score < 75 and len(scores) >= 5

    return {
        "overall_trend": trend,
        "rolling_average": round(avg_score, 1),
        "plateau_risk": plateau_risk,
        "session_count": len(scores),
        "last_updated": datetime.now().isoformat()
    }
