from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class SessionStoreError(RuntimeError):
    pass


class SessionStoreConflictError(SessionStoreError):
    pass


class EventStoreError(RuntimeError):
    pass


class ProgressStoreError(RuntimeError):
    pass


class TrainingPlanStoreError(RuntimeError):
    pass


@runtime_checkable
class SessionStore(Protocol):
    def create(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None: ...
    def upsert(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None: ...
    def get(self, session_id: str, *, org_id: str | None = None) -> dict[str, Any] | None: ...
    def list_all(self, *, org_id: str | None = None) -> list[dict[str, Any]]: ...


@runtime_checkable
class EventStore(Protocol):
    def append(self, session_id: str, event: dict[str, Any], *, org_id: str | None = None) -> None: ...
    def replace(self, session_id: str, events: list[dict[str, Any]], *, org_id: str | None = None) -> None: ...
    def list_events(self, session_id: str, *, org_id: str | None = None) -> list[dict[str, Any]]: ...


@runtime_checkable
class ProgressStore(Protocol):
    def upsert(self, learner_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None: ...
    def get(self, learner_id: str, *, org_id: str | None = None) -> dict[str, Any] | None: ...


@runtime_checkable
class TrainingPlanStore(Protocol):
    def create(self, plan: dict[str, Any]) -> None: ...
    def update(self, plan_id: str, payload: dict[str, Any]) -> None: ...
    def get(self, plan_id: str) -> dict[str, Any] | None: ...
    def list_all(self, *, org_id: str | None = None, learner_id: str | None = None) -> list[dict[str, Any]]: ...
    def delete(self, plan_id: str) -> None: ...
