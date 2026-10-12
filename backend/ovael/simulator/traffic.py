"""Traffic simulator: synthetic sandbox flows through the REAL pipeline.

Nothing about detection is faked. Flows are generated from the same class profiles as the bootstrap
dataset, then go through detect(), the decision table, storage, auto-defense (simulate mode) and the
WebSocket like sensor flows do. Every detection is stored with origin="simulated" and the dashboard
labels it, so simulated and real traffic are never confused.

Once a source is blocked its traffic stops, which is what the demo order in the architecture asks
for: attack -> alert -> block -> traffic stops -> undo.
"""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from sqlalchemy import select

from ..api.schemas import ActionOut
from ..core.context import AppContext
from ..db.models import DefenseAction
from ..ml.synthetic import ATTACKER_IPS, sample_flow
from ..services import pipeline

log = logging.getLogger(__name__)

# phase = (class, seconds, flows per second)
SCENARIOS: dict[str, list[tuple[str, float, float]]] = {
    "normal": [("benign", 1.0, 6)],
    "dos_flood": [("benign", 0.15, 6), ("dos_flood", 0.85, 40)],
    "slow_dos": [("benign", 0.15, 6), ("slow_dos", 0.85, 8)],
    "port_scan": [("benign", 0.15, 6), ("port_scan", 0.85, 25)],
    "brute_force": [("benign", 0.15, 6), ("brute_force", 0.85, 10)],
    "web_attack": [("benign", 0.15, 6), ("web_attack", 0.85, 6)],
    "novel": [("benign", 0.15, 6), ("novel", 0.85, 5)],
    "full_demo": [("benign", 0.12, 6), ("port_scan", 0.2, 25), ("benign", 0.06, 6),
                  ("dos_flood", 0.25, 40), ("benign", 0.06, 6), ("novel", 0.16, 5),
                  ("brute_force", 0.15, 10)],
}
TICK_S = 0.25


class Simulator:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.task: asyncio.Task | None = None
        self.status: dict = {"running": False}

    def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
        self.status = {"running": False}

    def start(self, scenario: str, duration_s: float) -> dict:
        if scenario not in SCENARIOS:
            raise KeyError(scenario)
        self.stop()
        self.task = asyncio.create_task(self._run(scenario, duration_s), name=f"simulate-{scenario}")
        self.status = {"running": True, "scenario": scenario, "duration_s": duration_s,
                       "started_at": time.time(), "phase": None}
        return self.status

    async def _reset_sandbox(self) -> None:
        """Each run starts clean: blocks left on the simulated attackers by earlier runs are lifted
        (and logged as undone by the simulator), otherwise the attack would never be seen."""
        async with self.ctx.db.session() as session:
            stale = list(await session.scalars(select(DefenseAction).where(
                DefenseAction.target_ip.in_(list(ATTACKER_IPS.values())),
                DefenseAction.status.in_(("applied", "simulated")))))
            for a in stale:
                await self.ctx.defense.undo(session, a.id, "simulator reset")
            await session.commit()
        for a in stale:
            await self.ctx.bus.publish("defense_action", ActionOut.model_validate(a).model_dump(mode="json"))

    async def _run(self, scenario: str, duration_s: float) -> None:
        rng = np.random.default_rng()
        await self._reset_sandbox()
        phases = SCENARIOS[scenario]
        total = sum(p[1] for p in phases)
        try:
            for cls, share, rate in phases:
                self.status["phase"] = cls
                end = time.monotonic() + duration_s * share / total
                await self.ctx.bus.publish("simulation", {"scenario": scenario, "phase": cls})
                carry = 0.0
                while time.monotonic() < end:
                    blocked = cls in ATTACKER_IPS and await self.ctx.defense.is_blocked(ATTACKER_IPS[cls])
                    carry += rate * TICK_S
                    n, carry = int(carry), carry - int(carry)
                    items = []
                    for _ in range(n):
                        # benign background keeps flowing during attacks; a blocked attacker stops
                        kind = cls if not blocked else "benign"
                        f, meta = sample_flow(kind, rng)
                        items.append({"features": f, "meta": meta})
                    if cls != "benign" and not blocked and rng.random() < 0.5:
                        f, meta = sample_flow("benign", rng)
                        items.append({"features": f, "meta": meta})
                    if items:
                        await pipeline.process(self.ctx, "network", items, origin="simulated")
                    await asyncio.sleep(TICK_S)
            await self.ctx.bus.publish("simulation", {"scenario": scenario, "phase": "done"})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("simulation %s failed", scenario)
        finally:
            self.status = {"running": False}
