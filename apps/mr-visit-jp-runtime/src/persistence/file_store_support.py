from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None  # type: ignore[assignment]


LOGGER = logging.getLogger("mr_visit_jp_runtime.persistence")


@contextmanager
def advisory_file_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_json_object(
    path: Path,
    *,
    entity_name: str,
    identifier_name: str,
    identifier_value: str,
    error_type: type[RuntimeError],
) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise error_type(
            f"Corrupted {entity_name} payload for {identifier_name}={identifier_value} "
            f"at {path} (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    except OSError as exc:
        raise error_type(
            f"Failed to read {entity_name} payload for {identifier_name}={identifier_value} "
            f"at {path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise error_type(
            f"Corrupted {entity_name} payload for {identifier_name}={identifier_value} "
            f"at {path}: expected JSON object"
        )
    return payload


def load_jsonl_objects(
    path: Path,
    *,
    entity_name: str,
    identifier_name: str,
    identifier_value: str,
    error_type: type[RuntimeError],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise error_type(
                        f"Corrupted {entity_name} payload for {identifier_name}={identifier_value} "
                        f"at {path} line {line_number} (column {exc.colno}): {exc.msg}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise error_type(
                        f"Corrupted {entity_name} payload for {identifier_name}={identifier_value} "
                        f"at {path} line {line_number}: expected JSON object"
                    )
                payloads.append(payload)
    except OSError as exc:
        raise error_type(
            f"Failed to read {entity_name} payload for {identifier_name}={identifier_value} "
            f"at {path}: {exc}"
        ) from exc
    return payloads
