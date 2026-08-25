from __future__ import annotations

import threading
import time

from course_planner.jobs import PlannerJobManager
from course_planner.persistence import database_ready, planner_checkpointer


def _wait_for(manager: PlannerJobManager, job_id: str, statuses: set[str]) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}")


def test_sqlite_checkpointer_and_job_result_survive_connections(tmp_path, monkeypatch):
    database = tmp_path / "planner.sqlite3"
    monkeypatch.setenv("PLANNER_DATABASE_PATH", str(database))

    with planner_checkpointer() as saver:
        assert saver is not None
    manager = PlannerJobManager()
    try:
        job = manager.submit(
            "test",
            {"profile": {"name": "Test", "dars_text": "private raw text"}},
            lambda payload, progress, cancel: {"status": "completed", "value": 42},
        )
        completed = _wait_for(manager, job["id"], {"completed"})
        assert completed["result"] == {"status": "completed", "value": 42}
        assert database_ready() == (True, str(database))
        stored = database.read_bytes()
        assert b"private raw text" not in stored
    finally:
        manager.shutdown()


def test_running_job_can_be_cancelled_at_a_safe_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNER_DATABASE_PATH", str(tmp_path / "jobs.sqlite3"))
    started = threading.Event()

    def runner(payload, progress, cancel):
        started.set()
        cancel.wait(timeout=2)
        return {"status": "completed"}

    manager = PlannerJobManager()
    try:
        job = manager.submit("test", {}, runner)
        assert started.wait(timeout=1)
        cancelling = manager.cancel(job["id"])
        assert cancelling and cancelling["status"] in {"cancelling", "cancelled"}
        cancelled = _wait_for(manager, job["id"], {"cancelled"})
        assert "cancel" in cancelled["message"].lower()
    finally:
        manager.shutdown()


def test_late_cancellation_update_cannot_overwrite_terminal_status(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLANNER_DATABASE_PATH", str(tmp_path / "terminal.sqlite3"))
    manager = PlannerJobManager()
    try:
        job = manager.submit(
            "test",
            {},
            lambda payload, progress, cancel: {"status": "completed"},
        )
        completed = _wait_for(manager, job["id"], {"completed"})

        manager._update(
            job["id"],
            status="cancelling",
            message="Late cancellation request.",
            active_only=True,
        )

        assert manager.get(job["id"])["status"] == completed["status"]
    finally:
        manager.shutdown()
