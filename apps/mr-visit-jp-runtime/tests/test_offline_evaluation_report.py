from __future__ import annotations

from offline_evaluation_report import (
    build_offline_evaluation_report,
    build_offline_profile_deltas,
    render_offline_evaluation_report_text,
)


def test_build_offline_evaluation_report_exposes_dataset_and_profile_deltas() -> None:
    report = build_offline_evaluation_report()

    assert report["domain_id"] == "mr_visit_jp"
    assert report["offline_dataset"]["fixture_count"] >= 10
    assert report["offline_dataset"]["coverage"]["scenarios"]["missing"] == []
    deltas = build_offline_profile_deltas(report)
    assert len(deltas) >= 1
    first_delta = deltas[0]
    assert first_delta["baseline_profile_id"] == report["default_profile_id"]
    assert "fixture_pass_rate_delta" in first_delta


def test_render_offline_evaluation_report_text_mentions_coverage_gaps() -> None:
    report = build_offline_evaluation_report()
    rendered = render_offline_evaluation_report_text(report)

    assert "Offline dataset:" in rendered
    assert "Coverage gaps:" in rendered
    assert "Offline gate deltas:" in rendered
    assert report["default_profile_id"] in rendered
