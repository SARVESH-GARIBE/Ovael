"""WS /ws - live events for the dashboard.

Messages are JSON: {"type": ..., "ts": ..., "source": <instance>, "data": {...}}.
The client may send {"type": "ping"} and gets {"type": "pong"}; the server also sends a heartbeat
every 20 s so proxies do not close an idle connection.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
log = logging.getLogger(__name__)
HEARTBEAT_S = 20


@router.websocket("/ws")
async def events(ws: WebSocket) -> None:
    ctx = ws.app.state.ctx
    await ws.accept()
    await ws.send_json({"type": "hello", "data": {"instance": ctx.settings.instance_id}})

    async def receive() -> None:
        while True:
            msg = await ws.receive_text()
            try:
                if json.loads(msg).get("type") == "ping":
                    await ws.send_json({"type": "pong"})
            except (ValueError, AttributeError):
                pass

    async with ctx.bus.subscribe() as sub:
        reader = asyncio.create_task(receive())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), HEARTBEAT_S)
                except asyncio.TimeoutError:
                    event = {"type": "heartbeat", "data": {"dropped": sub.dropped}}
                if reader.done():
                    break
                await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader.cancel()
