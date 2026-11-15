"""SSE publishing for jobs: `job.updated`, `job.removed` and `queue.updated`."""

from __future__ import annotations

from app.events import EventBroadcaster
from app.jobs.models import Job


class JobEvents:
    def __init__(self, broadcaster: EventBroadcaster) -> None:
        self._broadcaster = broadcaster

    def job_updated(self, job: Job) -> None:
        self._broadcaster.publish("job.updated", job.to_dict())

    def job_removed(self, job_id: str) -> None:
        self._broadcaster.publish("job.removed", {"id": job_id})

    def queue_updated(self, *, active: int, queued: int) -> None:
        self._broadcaster.publish("queue.updated", {"active": active, "queued": queued})
