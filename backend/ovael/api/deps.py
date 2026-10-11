"""Request dependencies: the app context and the two bearer-token roles.

* admin  - review decisions, undo, retrain, promote, simulator
* sensor - posting flows from the sandbox sensor

When a token is not configured (development), that role is open and the actor is recorded as
"dev". Production sets both (startup logs a warning if it does not).
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request

from ..core.context import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def _require(token_attr: str, role: str):
    def dep(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
        expected = getattr(ctx.settings, token_attr)
        if expected is None:
            return "dev"
        given = _bearer(request)
        if not given or not hmac.compare_digest(given, expected):
            raise HTTPException(401, f"{role} token required", headers={"WWW-Authenticate": "Bearer"})
        return role
    return dep


require_admin = _require("admin_token", "admin")
require_sensor = _require("sensor_token", "sensor")


def client_ip(request: Request) -> str:
    # nginx sets X-Real-IP; it is the only hop allowed to reach the API containers.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
