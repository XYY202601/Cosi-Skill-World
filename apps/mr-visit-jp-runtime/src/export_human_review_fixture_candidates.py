from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from persistence.file_store_support import atomic_write_text
from persistence.store_factory import build_runtime_store_bundle
from runtime_config import resolve_runtime_data_dir
from scenarios.asset_loader import get_domain_bundle
from services.human_review_feedback import HumanReviewFeedbackService


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests" / "transcripts"


@dataclass
class ExportSummary:
    discovered_candidates: int = 0
    ready_candidates: int = 0
    written: int = 0
    skipped_existing: int = 0
    skipped_not_ready: int = 0
    invalid_candidates: int = 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export human-review fixture candidates into tests/transcripts/<bucket>/ JSON fixtures."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help=(
            "Runtime data directory. Defaults to MR_RUNTIME_DATA_DIR or "
            "apps/mr-visit-jp-runtime/.data."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Fixture output directory. Defaults to tests/transcripts.",
    )
    parser.add_argument(
        "--org-id",
        help="Optional organization id scope for multi-tenant runtime stores.",
    )
    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument(
        "--latest-only",
        action="store_true",
        default=True,
        help="Export only latest version of each human-review record (default).",
    )
    version_group.add_argument(
        "--all-versions",
        dest="latest_only",
        action="store_false",
        help="Export all feedback record versions.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files without writing. This is the default mode.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Write fixture files to output directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing fixture files.",
    )
    return parser


def _resolve_relative_fixture_path(raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("fixture_path must be a non-empty string")
    normalized = Path(raw_path.strip())
    if normalized.is_absolute():
        raise ValueError("fixture_path must be relative")
    if ".." in normalized.parts:
        raise ValueError("fixture_path cannot include `..` segments")
    if len(normalized.parts) < 2:
        raise ValueError("fixture_path must include bucket and file name")
    if normalized.suffix != ".json":
        raise ValueError("fixture_path must end with .json")
    return normalized


def _validate_fixture_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("fixture payload must be an object")
    required_keys = {"name", "finish_reason", "scenario_focus_subskills", "turns", "expected", "metadata"}
    missing = sorted(required_keys - set(payload.keys()))
    if missing:
        raise ValueError(f"fixture payload missing required keys: {missing}")
    return payload


def _render_summary(summary: ExportSummary, *, apply_mode: bool) -> str:
    mode = "apply" if apply_mode else "dry-run"
    return (
        "[export-human-review-fixture-candidates] "
        f"mode={mode} "
        f"discovered={summary.discovered_candidates} "
        f"ready={summary.ready_candidates} "
        f"written={summary.written} "
        f"skipped_existing={summary.skipped_existing} "
        f"skipped_not_ready={summary.skipped_not_ready} "
        f"invalid={summary.invalid_candidates}"
    )


def run(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else resolve_runtime_data_dir()
    output_dir = args.output_dir.expanduser().resolve()
    apply_mode = bool(args.apply)

    store_bundle = build_runtime_store_bundle(data_dir)
    service = HumanReviewFeedbackService(
        root_dir=data_dir / "human_review_feedback",
        session_store=store_bundle.session_store,
        domain_bundle=get_domain_bundle(),
    )

    payload = service.build_fixture_candidates(
        org_id=args.org_id,
        latest_only=bool(args.latest_only),
    )
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise RuntimeError("candidate payload is invalid: `candidates` is not a list")

    summary = ExportSummary(discovered_candidates=len(candidates))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            summary.invalid_candidates += 1
            continue
        if not bool(candidate.get("ready", False)):
            summary.skipped_not_ready += 1
            continue
        summary.ready_candidates += 1

        try:
            relative_path = _resolve_relative_fixture_path(candidate.get("fixture_path"))
            fixture_payload = _validate_fixture_payload(candidate.get("fixture"))
        except ValueError as exc:
            summary.invalid_candidates += 1
            print(
                "[export-human-review-fixture-candidates] "
                f"invalid candidate_id={candidate.get('candidate_id')} reason={exc}"
            )
            continue

        target_path = output_dir / relative_path
        if target_path.exists() and not args.overwrite:
            summary.skipped_existing += 1
            print(
                "[export-human-review-fixture-candidates] "
                f"skip existing path={target_path}"
            )
            continue

        if apply_mode:
            atomic_write_text(
                target_path,
                json.dumps(fixture_payload, ensure_ascii=False, indent=2) + "\n",
            )
            summary.written += 1
            print(
                "[export-human-review-fixture-candidates] "
                f"wrote path={target_path}"
            )
        else:
            print(
                "[export-human-review-fixture-candidates] "
                f"plan path={target_path}"
            )

    print(_render_summary(summary, apply_mode=apply_mode))
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
