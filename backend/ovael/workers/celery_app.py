"""Celery workers for slow work: website scans and retraining (two queues).

    celery -A ovael.workers.celery_app worker -Q scans -c 2      # scan workers
    celery -A ovael.workers.celery_app worker -Q training -c 1   # retrain worker

Scale scan workers on queue depth, not on a schedule (architecture section 7.3).
"""

from __future__ import annotations

import asyncio

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from ..config import get_settings

settings = get_settings()
celery_app = Celery("ovael", broker=settings.celery_broker_url or "memory://")
celery_app.conf.update(
    task_acks_late=True,  # a crashed worker's job is redelivered
    worker_prefetch_multiplier=1,  # one slow scan never hoards queued ones
    task_time_limit=int(settings.scan_timeout_s) + 120,
    task_routes={"ovael.scan_website": {"queue": "scans"}, "ovael.retrain": {"queue": "training"}},
)

_loop: asyncio.AbstractEventLoop | None = None
_ctx = None


@worker_process_init.connect
def _init(**_):
    global _loop, _ctx
    from ..core.context import build_context
    from ..core.logging import setup_logging

    setup_logging(settings.log_level)
    _loop = asyncio.new_event_loop()
    # Workers publish events through Redis but never listen to them.
    _ctx = _loop.run_until_complete(build_context(settings, listen=False))


@worker_process_shutdown.connect
def _shutdown(**_):
    if _ctx is not None:
        _loop.run_until_complete(_ctx.close())


@celery_app.task(name="ovael.scan_website")
def scan_website(scan_id: str) -> None:
    from ..services.scans import run_scan

    _loop.run_until_complete(run_scan(_ctx, scan_id))


@celery_app.task(name="ovael.retrain")
def retrain(module: str) -> dict:
    from ..services.learning import run_retrain

    return _loop.run_until_complete(run_retrain(_ctx, module))
