"""Background jobs: website scans and retraining. Neither ever runs on the live detection path.

* Celery (OVAEL_CELERY_BROKER_URL set): jobs go to a queue and a pool of workers picks them up.
  Add workers when queue depth grows; scans and retrains use separate queues so a long retrain
  never holds up scans.
* In-process (default): jobs run as asyncio tasks in the API process, scans capped by a
  semaphore, retraining in a thread. Fine for one server, which is where the system starts.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class LocalJobRunner:
    def __init__(self, ctx):
        self.ctx = ctx
        self._tasks: set[asyncio.Task] = set()
        self._scan_sem = asyncio.Semaphore(ctx.settings.max_concurrent_scans)
        self._retraining: set[str] = set()

    def _spawn(self, coro, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def submit_scan(self, scan_id: str) -> None:
        from ..services.scans import run_scan

        async def _run():
            async with self._scan_sem:
                await run_scan(self.ctx, scan_id)

        self._spawn(_run(), f"scan-{scan_id}")

    async def submit_retrain(self, module: str) -> bool:
        if module in self._retraining:
            return False
        from ..services.learning import run_retrain

        async def _run():
            self._retraining.add(module)
            try:
                await run_retrain(self.ctx, module)
            finally:
                self._retraining.discard(module)

        self._spawn(_run(), f"retrain-{module}")
        return True

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()


class CeleryJobRunner:
    def __init__(self, ctx):
        from ..workers.celery_app import celery_app

        self.app = celery_app

    async def submit_scan(self, scan_id: str) -> None:
        self.app.send_task("ovael.scan_website", args=[scan_id], queue="scans")

    async def submit_retrain(self, module: str) -> bool:
        self.app.send_task("ovael.retrain", args=[module], queue="training")
        return True

    async def stop(self) -> None:
        pass


def make_job_runner(ctx):
    if ctx.settings.celery_broker_url:
        return CeleryJobRunner(ctx)
    return LocalJobRunner(ctx)
