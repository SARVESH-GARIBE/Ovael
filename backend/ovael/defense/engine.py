"""Automatic defense policy (architecture section 5).

Fires only when ALL of these hold:
  * module is network and defense_mode is not "off"
  * risk_level is high AND both models agree (classifier says attack, anomaly detector says unusual)
  * the attack family allows auto-defense
  * the source is inside the sandbox subnet (nothing outside the sandbox is ever touched)
  * the source is not already blocked

The public API process never runs firewall commands. In "agent" mode it asks the defense agent
(a separate container in the victim's network namespace with NET_ADMIN) over HTTP. In "simulate"
mode it records the action without touching anything, which is what the demo and tests use.
Every action is logged with the detection that caused it and can be undone.
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from ..config import Settings
from ..core import metrics
from ..core.cache import Cache
from ..db.models import DefenseAction
from ..orchestrator import family_for

log = logging.getLogger(__name__)


class DefenseEngine:
    def __init__(self, settings: Settings, cache: Cache):
        self.settings = settings
        self.cache = cache
        self.subnet = ipaddress.ip_network(settings.sandbox_subnet)

    def _in_sandbox(self, ip: str | None) -> bool:
        try:
            return ip is not None and ipaddress.ip_address(ip) in self.subnet
        except ValueError:
            return False

    async def is_blocked(self, ip: str | None) -> bool:
        return bool(ip) and bool(await self.cache.get_json(f"blocked:{ip}"))

    def eligible(self, result, src_ip: str | None) -> tuple[bool, str]:
        if self.settings.defense_mode == "off":
            return False, "defense disabled"
        if result.module != "network":
            return False, "not a network detection"
        if result.risk_level != "high" or not result.models_agree:
            return False, "needs high risk with both models agreeing"
        if not family_for("network", result.label).auto_defense:
            return False, "family does not allow auto-defense"
        if not self._in_sandbox(src_ip):
            return False, "source outside sandbox"
        return True, "ok"

    async def _agent(self, path: str, ip: str) -> None:
        headers = {"Authorization": f"Bearer {self.settings.defense_token}"} if self.settings.defense_token else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{self.settings.defense_agent_url}{path}", json={"ip": ip}, headers=headers)
            r.raise_for_status()

    async def maybe_block(self, session, result, detection_id: str, incident_id: str | None,
                          src_ip: str | None) -> DefenseAction | None:
        ok, _ = self.eligible(result, src_ip)
        if not ok or await self.is_blocked(src_ip):
            return None
        # Several instances can see the same flood at once; only the first may act.
        if not await self.cache.acquire(f"block:{src_ip}", 15):
            return None
        # The database is the record: a block that outlived a cache flush or restart still counts.
        existing = await session.scalar(select(DefenseAction.id).where(
            DefenseAction.target_ip == src_ip, DefenseAction.status.in_(("applied", "simulated"))).limit(1))
        if existing:
            await self.cache.set_json(f"blocked:{src_ip}", {"action": existing}, ttl_s=7 * 24 * 3600)
            return None
        mode = "agent" if self.settings.defense_mode == "agent" and self.settings.defense_agent_url else "simulate"
        action = DefenseAction(action="block", target_ip=src_ip, mode=mode, detection_id=detection_id,
                               incident_id=incident_id,
                               reason=f"{result.family_name}: risk {result.risk_score} (high), both models agree")
        try:
            if mode == "agent":
                await self._agent("/block", src_ip)
                action.status = "applied"
            else:
                action.status = "simulated"
            await self.cache.set_json(f"blocked:{src_ip}", {"action": action.id}, ttl_s=7 * 24 * 3600)
        except Exception as exc:
            log.error("block %s failed: %s", src_ip, exc)
            action.status, action.error = "failed", str(exc)
        session.add(action)
        metrics.DEFENSE_ACTIONS.labels("block", action.status).inc()
        return action

    async def undo(self, session, action_id: str, actor: str) -> DefenseAction | None:
        action = await session.get(DefenseAction, action_id)
        if action is None:
            return None
        if action.status not in ("applied", "simulated"):
            raise ValueError(f"action is {action.status}; nothing to undo")
        if action.mode == "agent":
            await self._agent("/unblock", action.target_ip)
        action.status = "undone"
        action.undone_at = datetime.now(timezone.utc)
        action.undone_by = actor
        await self.cache.delete(f"blocked:{action.target_ip}")
        await self.cache.release(f"block:{action.target_ip}")
        metrics.DEFENSE_ACTIONS.labels("undo", "done").inc()
        return action

    async def warm(self, db) -> int:
        """Load active blocks into the cache at startup, so live events report them correctly."""
        async with db.session() as session:
            blocks = await self.active_blocks(session)
        for a in blocks:
            await self.cache.set_json(f"blocked:{a.target_ip}", {"action": a.id}, ttl_s=7 * 24 * 3600)
        return len(blocks)

    async def active_blocks(self, session) -> list[DefenseAction]:
        rows = await session.scalars(select(DefenseAction).where(DefenseAction.status.in_(("applied", "simulated"))))
        return list(rows)
