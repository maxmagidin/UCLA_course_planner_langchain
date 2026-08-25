"""Bounded, SQLite-backed background jobs for long planning horizons."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from course_planner.persistence import connect_database

JobRunner = Callable[
    [dict[str, Any], Callable[[int, str], None], threading.Event],
    dict[str, Any],
]


class JobQueueFull(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive_env_int(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


class PlannerJobManager:
    """Small local job runner; durable metadata, bounded in-process workers."""

    def __init__(self) -> None:
        self.max_workers = _positive_env_int("PLANNER_JOB_WORKERS", 2, 8)
        self.max_queued = _positive_env_int("PLANNER_MAX_QUEUED_JOBS", 20, 200)
        self.retention_days = _positive_env_int("PLANNER_JOB_RETENTION_DAYS", 7, 90)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="planner-job",
        )
        self._lock = threading.Lock()
        self._futures: dict[str, Future] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._closed = False
        self._setup()

    def _setup(self) -> None:
        connection = connect_database()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS planner_jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS planner_jobs_updated_idx ON planner_jobs(updated_at)"
            )
            connection.execute(
                """
                UPDATE planner_jobs
                SET status = 'interrupted',
                    message = 'Server restarted before this job finished.',
                    updated_at = ?
                WHERE status IN ('queued', 'running', 'cancelling')
                """,
                (_now(),),
            )
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            ).isoformat()
            connection.execute(
                """
                DELETE FROM planner_jobs
                WHERE updated_at < ?
                  AND status IN ('completed', 'failed', 'cancelled', 'interrupted')
                """,
                (cutoff,),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _sanitized_payload(payload: dict[str, Any]) -> dict[str, Any]:
        sanitized = deepcopy(payload)
        profile = sanitized.get("profile")
        if isinstance(profile, dict):
            profile.pop("dars_text", None)
        return sanitized

    def submit(
        self, kind: str, payload: dict[str, Any], runner: JobRunner
    ) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("job manager is shutting down")
        connection = connect_database()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            ).isoformat()
            connection.execute(
                """
                DELETE FROM planner_jobs
                WHERE updated_at < ?
                  AND status IN ('completed', 'failed', 'cancelled', 'interrupted')
                """,
                (cutoff,),
            )
            active = connection.execute(
                "SELECT COUNT(*) FROM planner_jobs WHERE status IN ('queued', 'running', 'cancelling')"
            ).fetchone()[0]
            if active >= self.max_queued:
                raise JobQueueFull("planner job queue is full; try again shortly")
            job_id = str(uuid4())
            timestamp = _now()
            connection.execute(
                """
                INSERT INTO planner_jobs (
                    id, kind, status, progress, message, request_json,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, 'Waiting for a planner worker.', ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    json.dumps(self._sanitized_payload(payload), separators=(",", ":")),
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        cancel_event = threading.Event()
        future = self._executor.submit(
            self._execute, job_id, payload, runner, cancel_event
        )
        with self._lock:
            self._cancel_events[job_id] = cancel_event
            self._futures[job_id] = future
        future.add_done_callback(lambda _: self._forget_runtime(job_id))
        return self.get(job_id) or {"id": job_id, "status": "queued"}

    def _forget_runtime(self, job_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(job_id, None)
            self._futures.pop(job_id, None)

    def _execute(
        self,
        job_id: str,
        payload: dict[str, Any],
        runner: JobRunner,
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set():
            self._update(
                job_id, status="cancelled", message="Cancelled before starting."
            )
            return
        self._update(job_id, status="running", progress=1, message="Planning started.")

        def progress(value: int, message: str) -> None:
            self._update(
                job_id,
                status="cancelling" if cancel_event.is_set() else "running",
                progress=max(1, min(99, value)),
                message=message,
            )

        try:
            result = runner(payload, progress, cancel_event)
            if cancel_event.is_set():
                self._update(
                    job_id,
                    status="cancelled",
                    message="Cancelled after the active planner step finished.",
                )
                return
            self._update(
                job_id,
                status="completed",
                progress=100,
                message="Planning finished.",
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 - background failures become job records
            self._update(
                job_id,
                status="cancelled" if cancel_event.is_set() else "failed",
                message="Planning cancelled."
                if cancel_event.is_set()
                else "Planning failed.",
                error=str(exc)[:2_000],
            )

    def _update(
        self,
        job_id: str,
        *,
        status: str,
        message: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        error: str = "",
        active_only: bool = False,
    ) -> None:
        assignments = ["status = ?", "message = ?", "updated_at = ?", "error = ?"]
        values: list[Any] = [status, message, _now(), error]
        if progress is not None:
            assignments.append("progress = ?")
            values.append(progress)
        if result is not None:
            assignments.append("result_json = ?")
            values.append(json.dumps(result, separators=(",", ":")))
        values.append(job_id)
        connection = connect_database()
        try:
            where = "id = ?"
            if active_only:
                where += " AND status IN ('queued', 'running', 'cancelling')"
            connection.execute(
                f"UPDATE planner_jobs SET {', '.join(assignments)} WHERE {where}",
                values,
            )
            connection.commit()
        finally:
            connection.close()

    def get(self, job_id: str) -> dict[str, Any] | None:
        connection = connect_database()
        try:
            row = connection.execute(
                """
                SELECT id, kind, status, progress, message, result_json,
                       error, created_at, updated_at
                FROM planner_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        result = dict(row)
        raw_result = result.pop("result_json")
        result["result"] = json.loads(raw_result) if raw_result else None
        return result

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        if job is None or job["status"] not in {"queued", "running", "cancelling"}:
            return job
        with self._lock:
            event = self._cancel_events.get(job_id)
            future = self._futures.get(job_id)
        if event:
            event.set()
        cancelled_before_start = bool(future and future.cancel())
        self._update(
            job_id,
            status="cancelled" if cancelled_before_start else "cancelling",
            message=(
                "Cancelled before starting."
                if cancelled_before_start
                else "Cancellation requested; waiting for the active step to finish."
            ),
            active_only=True,
        )
        return self.get(job_id)

    def ready(self) -> dict[str, int | bool]:
        connection = connect_database()
        try:
            active = connection.execute(
                "SELECT COUNT(*) FROM planner_jobs WHERE status IN ('queued', 'running', 'cancelling')"
            ).fetchone()[0]
        finally:
            connection.close()
        return {
            "ready": not self._closed,
            "active_jobs": int(active),
            "max_workers": self.max_workers,
            "max_queued": self.max_queued,
        }

    def shutdown(self) -> None:
        self._closed = True
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


_manager: PlannerJobManager | None = None
_manager_lock = threading.Lock()


def get_job_manager() -> PlannerJobManager:
    global _manager
    with _manager_lock:
        if _manager is None or _manager._closed:
            _manager = PlannerJobManager()
        return _manager


def reset_job_manager_for_tests() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.shutdown()
        _manager = None
