from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
import json
import os
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from persistence.store_factory import build_runtime_store_bundle
from persistence.sql_stores import reset_runtime_sql_data
from providers import load_runtime_prompt_context_from_env
from runtime_config import env_flag_enabled, resolve_runtime_data_dir
from scenarios.asset_loader import get_domain_bundle
from services.demo_progress_seed import append_comprehensive_today_sessions
from services.evaluation_gate_service import EvaluationGateService
from services.progress_tracker import ProgressTracker

DEFAULT_LEARNER_IDS = ("learner_A", "learner_B", "learner_C")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed comprehensive training data for learners A/B/C into PostgreSQL. "
            "Each session is constrained to a configurable turn range (default: 5-10)."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help=(
            "Runtime data directory used only when MR_RUNTIME_PERSISTENCE_MODE=file. "
            "Ignored in sql mode."
        ),
    )
    parser.add_argument(
        "--learner-id",
        action="append",
        dest="learner_ids",
        help=(
            "Target learner id. Repeat this option to seed multiple learners. "
            "Defaults to learner_A, learner_B, learner_C."
        ),
    )
    parser.add_argument(
        "--sessions-per-learner",
        type=int,
        default=24,
        help=(
            "How many sessions to create for each learner. "
            "Use >= number of domain scenarios for full coverage. Default: 24."
        ),
    )
    parser.add_argument(
        "--min-turns",
        type=int,
        default=5,
        help="Minimum turns per generated session. Default: 5.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Maximum turns per generated session. Default: 10.",
    )
    parser.add_argument(
        "--anchor-now",
        help=(
            "Optional ISO datetime anchor for deterministic timestamp layout, "
            "for example 2026-05-01T18:00:00+09:00."
        ),
    )
    parser.add_argument(
        "--truncate-sql-first",
        action="store_true",
        help="Delete existing SQL runtime rows before seeding.",
    )
    parser.add_argument(
        "--allow-runtime-mode-mismatch",
        action="store_true",
        help=(
            "Allow seeding even when a running runtime reports a different persistence mode. "
            "By default, seeding aborts on mismatch to prevent writing data to a store "
            "that the UI is not reading."
        ),
    )
    return parser


def _resolve_learner_ids(raw_ids: Sequence[str] | None) -> tuple[str, ...]:
    if not raw_ids:
        return DEFAULT_LEARNER_IDS
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        learner_id = raw_id.strip() if raw_id else ""
        if not learner_id or learner_id in seen:
            continue
        normalized.append(learner_id)
        seen.add(learner_id)
    if not normalized:
        raise ValueError("No valid learner ids were provided")
    return tuple(normalized)


def _parse_anchor_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return datetime.fromisoformat(normalized)


def _read_running_runtime_mode() -> str | None:
    runtime_base = os.getenv("MR_VISIT_JP_RUNTIME_BASE", "http://127.0.0.1:8100").strip()
    if not runtime_base:
        return None
    url = f"{runtime_base.rstrip('/')}/healthz"
    try:
        with urlrequest.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    mode = payload.get("persistence_mode")
    if isinstance(mode, str) and mode.strip():
        return mode.strip().lower()
    return None


def run(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.sessions_per_learner <= 0:
        raise ValueError("--sessions-per-learner must be greater than 0")
    if args.min_turns <= 0:
        raise ValueError("--min-turns must be greater than 0")
    if args.max_turns < args.min_turns:
        raise ValueError("--max-turns must be greater than or equal to --min-turns")

    learner_ids = _resolve_learner_ids(args.learner_ids)
    anchor_now = _parse_anchor_now(args.anchor_now)

    data_dir = (args.data_dir or resolve_runtime_data_dir()).expanduser().resolve()
    store_bundle = build_runtime_store_bundle(data_dir)
    if store_bundle.mode != "sql":
        raise RuntimeError(
            "seed_training_data requires MR_RUNTIME_PERSISTENCE_MODE=sql "
            "so training data is persisted to PostgreSQL."
        )
    running_runtime_mode = _read_running_runtime_mode()
    if (
        running_runtime_mode is not None
        and running_runtime_mode != store_bundle.mode
        and not args.allow_runtime_mode_mismatch
    ):
        raise RuntimeError(
            "Running runtime persistence_mode does not match seed target mode. "
            f"running={running_runtime_mode}, target={store_bundle.mode}. "
            "Restart the stack so runtime uses SQL mode (for example `make stack-up`), "
            "or pass --allow-runtime-mode-mismatch if you intentionally want this."
        )
    if store_bundle.sql_engine is None:
        raise RuntimeError("SQL engine is unavailable in sql persistence mode")
    if args.truncate_sql_first:
        reset_runtime_sql_data(store_bundle.sql_engine)

    bundle = get_domain_bundle()
    scenario_count = len(bundle.scenarios)
    if args.sessions_per_learner < scenario_count:
        raise ValueError(
            "--sessions-per-learner must be >= number of scenarios "
            f"({scenario_count}) for full-spectrum coverage."
        )

    prompt_context = EvaluationGateService(
        domain_bundle=bundle,
        session_store=store_bundle.session_store,
        requested_prompt_context=load_runtime_prompt_context_from_env(),
        allow_blocked_rollout=env_flag_enabled("MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT"),
    ).effective_prompt_context
    progress_tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        curriculum=bundle.curriculum,
        progress_store=store_bundle.progress_store,
    )

    for learner_id in learner_ids:
        created_session_ids = append_comprehensive_today_sessions(
            learner_id=learner_id,
            session_count=args.sessions_per_learner,
            min_turns=args.min_turns,
            max_turns=args.max_turns,
            bundle=bundle,
            progress_tracker=progress_tracker,
            session_store=store_bundle.session_store,
            event_store=store_bundle.event_store,
            prompt_context=prompt_context,
            anchor_now=anchor_now,
        )
        if len(created_session_ids) != args.sessions_per_learner:
            raise RuntimeError(
                f"Expected {args.sessions_per_learner} sessions for {learner_id}, "
                f"but created {len(created_session_ids)}."
            )

        turn_counts: list[int] = []
        for session_id in created_session_ids:
            payload = store_bundle.session_store.get(session_id)
            if not isinstance(payload, dict):
                raise RuntimeError(f"Missing generated session payload for session_id={session_id}")
            turn_count = int(payload.get("turn_count", 0))
            if turn_count < args.min_turns or turn_count > args.max_turns:
                raise RuntimeError(
                    f"Session {session_id} has turn_count={turn_count}, outside "
                    f"configured range [{args.min_turns}, {args.max_turns}]."
                )
            turn_counts.append(turn_count)

        snapshot = store_bundle.progress_store.get(learner_id) or {}
        total_sessions = int(snapshot.get("total_sessions", 0))
        print(
            "[seed-training-data] "
            f"learner_id={learner_id} "
            f"created_sessions={len(created_session_ids)} "
            f"turn_count_min={min(turn_counts)} "
            f"turn_count_max={max(turn_counts)} "
            f"total_sessions={total_sessions}"
        )

    print(
        "[seed-training-data] "
        f"mode={store_bundle.mode} "
        f"scenario_count={scenario_count} "
        f"prompt_profile={prompt_context['profile_id']}"
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
