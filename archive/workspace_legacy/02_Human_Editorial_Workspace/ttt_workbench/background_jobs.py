"""Background job runner for model-backed operations.

Keeps the UI responsive by moving long-running LLM calls onto
worker threads with cancellation support and visible job status.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Job:
    """Represents one background model operation."""
    job_id: str
    label: str            # e.g. "chunk-suggest", "analysis", "finalize"
    target: Callable[[], Any]
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    started_at: float | None = None
    finished_at: float | None = None
    future: Future | None = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.monotonic()
        return end - self.started_at

    @property
    def elapsed_display(self) -> str:
        secs = int(self.elapsed)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.future and not self.future.done():
            self.future.cancel()


class JobRunner:
    """Manages a pool of worker threads for model-backed operations."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ttt-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._on_change: Callable[[], None] | None = None

    def set_change_callback(self, callback: Callable[[], None]) -> None:
        """Called whenever the job list changes."""
        self._on_change = callback

    def submit(self, job: Job) -> Job:
        with self._lock:
            job.status = JobStatus.RUNNING
            job.started_at = time.monotonic()
            future = self._executor.submit(self._run_job, job)
            job.future = future
            self._jobs[job.job_id] = job
        if self._on_change:
            self._on_change()
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                job.cancel()
                job.status = JobStatus.CANCELLED
                job.finished_at = time.monotonic()
                if self._on_change:
                    self._on_change()
                return True
        return False

    def cancel_all(self) -> int:
        count = 0
        with self._lock:
            for job in self._jobs.values():
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    job.cancel()
                    job.status = JobStatus.CANCELLED
                    job.finished_at = time.monotonic()
                    count += 1
        if count and self._on_change:
            self._on_change()
        return count

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_jobs(self) -> list[Job]:
        with self._lock:
            return [
                job for job in self._jobs.values()
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING)
            ]

    def recent_jobs(self, limit: int = 10) -> list[Job]:
        with self._lock:
            finished = [
                job for job in self._jobs.values()
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            ]
            finished.sort(key=lambda j: j.finished_at or 0, reverse=True)
            return finished[:limit]

    def all_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def shutdown(self, wait: bool = True) -> None:
        self.cancel_all()
        self._executor.shutdown(wait=wait)

    def _run_job(self, job: Job) -> None:
        try:
            if job.cancel_event.is_set():
                job.status = JobStatus.CANCELLED
                return
            result = job.target()
            if job.cancel_event.is_set():
                job.status = JobStatus.CANCELLED
                return
            job.result = result
            job.status = JobStatus.COMPLETED
        except Exception as exc:
            job.error = str(exc)
            job.status = JobStatus.FAILED
        finally:
            job.finished_at = time.monotonic()
            if self._on_change:
                self._on_change()
