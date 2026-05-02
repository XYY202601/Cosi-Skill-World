from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from persistence.store_factory import build_runtime_store_bundle
from providers import load_runtime_prompt_context_from_env
from runtime_config import env_flag_enabled, resolve_runtime_data_dir
from scenarios.asset_loader import get_domain_bundle
from services.demo_progress_seed import (
    DEMO_LEARNER_SPECS,
    DemoLearnerSpec,
    append_comprehensive_today_sessions,
    ensure_demo_runtime_data,
)
from services.evaluation_gate_service import EvaluationGateService
from services.progress_tracker import ProgressTracker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed demo learner progress and session artifacts for mr-visit-jp-runtime.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override the target runtime data directory. Defaults to MR_RUNTIME_DATA_DIR or apps/mr-visit-jp-runtime/.data.",
    )
    parser.add_argument(
        "--learner-id",
        action="append",
        dest="learner_ids",
        help="Seed only the specified demo learner id. Repeat the flag to include multiple demo learners.",
    )
    parser.add_argument(
        "--list-learners",
        action="store_true",
        help="Print the available demo learner ids and exit.",
    )
    parser.add_argument(
        "--append-today-sessions",
        type=int,
        default=0,
        help=(
            "Append a comprehensive same-day demo batch to one learner. "
            "Use with --append-today-learner-id. Example: --append-today-sessions 25."
        ),
    )
    parser.add_argument(
        "--append-today-learner-id",
        default="learner_demo_001",
        help=(
            "Target learner id for --append-today-sessions. "
            "Defaults to learner_demo_001 so the main dashboard gets denser recent history."
        ),
    )
    return parser


def _resolve_target_specs(learner_ids: Sequence[str] | None) -> tuple[DemoLearnerSpec, ...]:
    if not learner_ids:
        return DEMO_LEARNER_SPECS

    requested_ids: list[str] = []
    seen_ids: set[str] = set()
    for learner_id in learner_ids:
        normalized_id = learner_id.strip() if learner_id else ""
        if not normalized_id or normalized_id in seen_ids:
            continue
        requested_ids.append(normalized_id)
        seen_ids.add(normalized_id)

    spec_by_id = {spec.learner_id: spec for spec in DEMO_LEARNER_SPECS}
    missing_ids = sorted(set(requested_ids) - spec_by_id.keys())
    if missing_ids:
        available_ids = ", ".join(sorted(spec_by_id))
        raise ValueError(
            f"Unknown learner ids: {', '.join(missing_ids)}. Available demo learners: {available_ids}"
        )
    return tuple(spec_by_id[learner_id] for learner_id in requested_ids)


def _print_available_learners() -> None:
    for spec in DEMO_LEARNER_SPECS:
        print(
            f"{spec.learner_id}\t"
            f"sessions={spec.session_count}\t"
            f"days={spec.active_day_span}"
        )


def run(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_learners:
        _print_available_learners()
        return 0

    if args.append_today_sessions < 0:
        raise ValueError("--append-today-sessions must be >= 0")

    target_specs = (
        tuple()
        if args.append_today_sessions > 0 and not args.learner_ids
        else _resolve_target_specs(args.learner_ids)
    )
    bundle = get_domain_bundle()
    data_dir = (args.data_dir or resolve_runtime_data_dir()).expanduser().resolve()
    store_bundle = build_runtime_store_bundle(data_dir)
    session_store = store_bundle.session_store
    event_store = store_bundle.event_store
    progress_store = store_bundle.progress_store
    prompt_context = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=load_runtime_prompt_context_from_env(),
        allow_blocked_rollout=env_flag_enabled("MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT"),
    ).effective_prompt_context
    progress_tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        curriculum=bundle.curriculum,
        progress_store=progress_store,
    )

    if target_specs:
        ensure_demo_runtime_data(
            bundle=bundle,
            progress_tracker=progress_tracker,
            progress_store=progress_store,
            session_store=session_store,
            event_store=event_store,
            prompt_context=prompt_context,
            specs=target_specs,
        )

    appended_session_ids: list[str] = []
    if args.append_today_sessions > 0:
        appended_session_ids = append_comprehensive_today_sessions(
            learner_id=args.append_today_learner_id,
            session_count=args.append_today_sessions,
            bundle=bundle,
            progress_tracker=progress_tracker,
            session_store=session_store,
            event_store=event_store,
            prompt_context=prompt_context,
        )

    print(f"[seed-demo-data] data_dir={data_dir}")
    print(f"[seed-demo-data] prompt_profile={prompt_context['profile_id']}")
    for spec in target_specs:
        snapshot = progress_store.get(spec.learner_id) or {}
        total_sessions = int(snapshot.get("total_sessions", 0))
        history_count = len(snapshot.get("recent_history", [])) if isinstance(snapshot.get("recent_history"), list) else 0
        print(
            f"[seed-demo-data] learner_id={spec.learner_id} "
            f"total_sessions={total_sessions} recent_history={history_count}"
        )
    if appended_session_ids:
        appended_snapshot = progress_store.get(args.append_today_learner_id) or {}
        appended_total_sessions = int(appended_snapshot.get("total_sessions", 0))
        appended_history_count = (
            len(appended_snapshot.get("recent_history", []))
            if isinstance(appended_snapshot.get("recent_history"), list)
            else 0
        )
        print(
            f"[seed-demo-data] appended_today learner_id={args.append_today_learner_id} "
            f"count={len(appended_session_ids)} total_sessions={appended_total_sessions} "
            f"recent_history={appended_history_count}"
        )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
