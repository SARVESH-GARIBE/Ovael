"""Live event bus behind the /ws WebSocket.

Event types (architecture section 4.5): new_detection, defense_action, scan_complete,
model_retrained, plus review_item and incident_update for the dashboard.

Design for more than one API instance behind the load balancer:

* Each process keeps ONE upstream subscription (a Redis pub/sub channel) and fans events out to
  its local WebSocket clients through bounded per-client queues. 1,000 browsers cost one Redis
  subscription per instance, not 1,000.
* A detection made on instance A therefore reaches a browser connected to instance B, so the load
  balancer needs no sticky sessions.
* A slow client never slows the others: when its queue is full the oldest event is dropped and a
  counter goes up. The browser can reconcile through REST.

Without Redis the bus is purely in-process, which is correct for a single instance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from . import metrics

log = logging.getLogger(__name__)
CHANNEL = "ovael:events"


class Subscription:
    def __init__(self, maxsize: int):
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def offer(self, event: dict) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.dropped += 1
            metrics.WS_DROPPED.inc()
        self.queue.put_nowait(event)


class EventBus:
    def __init__(self, client_queue: int = 500, instance_id: str = "api"):
        self._subs: set[Subscription] = set()
        self.client_queue = client_queue
        self.instance_id = instance_id

    def _envelope(self, type_: str, data: dict) -> dict:
        return {"type": type_, "ts": time.time(), "source": self.instance_id, "data": data}

    def _fanout(self, event: dict) -> None:
        for sub in list(self._subs):
            sub.offer(event)

    async def publish(self, type_: str, data: dict) -> None:
        metrics.EVENTS_PUBLISHED.labels(type_).inc()
        self._fanout(self._envelope(type_, data))

    @asynccontextmanager
    async def subscribe(self):
        sub = Subscription(self.client_queue)
        self._subs.add(sub)
        metrics.WS_CLIENTS.inc()
        try:
            yield sub
        finally:
            self._subs.discard(sub)
            metrics.WS_CLIENTS.dec()

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class RedisEventBus(EventBus):
    def __init__(self, redis, **kw):
        super().__init__(**kw)
        self.redis = redis
        self._task: asyncio.Task | None = None

    async def publish(self, type_: str, data: dict) -> None:
        metrics.EVENTS_PUBLISHED.labels(type_).inc()
        await self.redis.publish(CHANNEL, json.dumps(self._envelope(type_, data), default=str))

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen(), name="event-bus-listener")

    async def _listen(self) -> None:
        while True:
            try:
                pubsub = self.redis.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        self._fanout(json.loads(msg["data"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("event bus listener lost Redis (%s); reconnecting", exc)
                await asyncio.sleep(1.0)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
