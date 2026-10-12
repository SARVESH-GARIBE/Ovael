"""Flow replayer: sends recorded flows to POST /api/flows the way the sensor does.

The sandbox has no live attack generators. Attack traffic enters it as REAL recorded flows
(CIC-IDS2017 after `ovael dataset import-cicids`), replayed with sandbox addresses through the same
authenticated sensor endpoint, the load balancer and every API replica. Normal traffic in the
sandbox is live: the client container browses the victim and the victim's sensor captures it.

    python -m ovael.cli replay --api http://nginx/api/flows --scenario full_demo --duration 60
"""

from __future__ import annotations

import logging
import time

import httpx
import numpy as np

from .config import Settings
from .ml.flow_source import get_flow_source
from .simulator.traffic import SCENARIOS

log = logging.getLogger(__name__)


def replay(settings: Settings, api_url: str, scenario: str, duration_s: float, token: str | None = None) -> dict:
    if scenario not in SCENARIOS:
        raise SystemExit(f"unknown scenario; choose one of {list(SCENARIOS)}")
    source = get_flow_source(settings)
    rng = np.random.default_rng()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    phases = SCENARIOS[scenario]
    total_share = sum(p[1] for p in phases)
    sent = alerts = 0
    blocked: set[str] = set()
    with httpx.Client(timeout=10.0, headers=headers) as client:
        for cls, share, rate in phases:
            end = time.monotonic() + duration_s * share / total_share
            log.info("phase %s (%s)", cls, source.name)
            while time.monotonic() < end:
                batch = []
                for _ in range(max(1, int(rate))):
                    features, meta = source.sample(cls if meta_ok(cls, blocked) else "benign", rng)
                    batch.append({"features": features, **meta})
                r = client.post(api_url, json={"flows": batch})
                r.raise_for_status()
                res = r.json()
                sent += res["accepted"]
                alerts += res["alerts"]
                blocked.update(res["blocked_sources"])
                time.sleep(1.0)
    return {"scenario": scenario, "flows": source.name, "sent": sent, "alerts": alerts, "blocked": sorted(blocked)}


def meta_ok(cls: str, blocked: set[str]) -> bool:
    """A blocked attacker's traffic stops reaching the victim, as with a real firewall drop."""
    from .ml.synthetic import ATTACKER_IPS

    return ATTACKER_IPS.get(cls) not in blocked
