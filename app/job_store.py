from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class JobState:
    job_id: str
    run_dir: Path
    status: str = "queued"
    stage: str = "대기 중"
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_requested: bool = False
    summary: dict[str, Any] = field(default_factory=lambda: {
        "total": 0, "quality": 0, "normal": 0, "trash": 0, "manual": 0
    })
    leads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "id": len(self.events),
            "type": event_type,
            "ts": time.time(),
            **payload,
        }
        self.events.append(event)
        self.changed.set()

    def set_progress(self, progress: float, stage: str, message: str = "") -> None:
        requested = max(0.0, min(100.0, float(progress)))
        self.progress = max(self.progress, requested)
        self.stage = stage
        self.message = message
        self.emit("progress", {
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "status": self.status,
            "summary": self.summary,
        })


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}

    def create(self, job_id: str, run_dir: Path) -> JobState:
        job = JobState(job_id=job_id, run_dir=run_dir)
        self.jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        return self.jobs.get(job_id)


STORE = JobStore()
