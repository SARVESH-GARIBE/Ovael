"""Everything a request handler or background job needs, built once per process."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Settings
from ..db.session import Database
from ..defense.engine import DefenseEngine
from ..ml.registry import ModelRegistry
from .cache import Cache
from .detect import DetectionEngine
from .events import EventBus, RedisEventBus

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    registry: ModelRegistry
    engine: DetectionEngine
    bus: EventBus
    cache: Cache
    defense: DefenseEngine
    redis: object | None = None
    jobs: object | None = None  # JobRunner, attached after construction
    scanner: object | None = None  # in-process WebsiteScanner, created lazily
    state: dict = field(default_factory=dict)  # per-process throttling state

    async def close(self) -> None:
        await self.bus.stop()
        if self.jobs is not None:
            await self.jobs.stop()
        if self.scanner is not None:
            await self.scanner.stop()
        await self.db.close()
        if self.redis is not None:
            await self.redis.aclose()


async def build_context(settings: Settings, *, listen: bool = True) -> AppContext:
    redis = None
    if settings.redis_url:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
    db = Database(settings)
    if settings.auto_create_schema:
        await db.create_schema()
    registry = ModelRegistry(settings.model_dir)
    cache = Cache(redis)
    bus = (RedisEventBus(redis, client_queue=settings.ws_client_queue, instance_id=settings.instance_id)
           if redis is not None else
           EventBus(client_queue=settings.ws_client_queue, instance_id=settings.instance_id))
    if listen:
        await bus.start()
    ctx = AppContext(settings=settings, db=db, registry=registry,
                     engine=DetectionEngine(registry, settings), bus=bus, cache=cache,
                     defense=DefenseEngine(settings, cache), redis=redis)
    from .jobs import make_job_runner

    ctx.jobs = make_job_runner(ctx)
    return ctx
