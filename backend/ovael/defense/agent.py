"""Defense agent: the only process allowed to change firewall rules.

Runs in its own container that shares the VICTIM container's network namespace and has NET_ADMIN
(see docker-compose.yml, profile "sandbox"). It is never reachable from the public network. It
refuses any address outside the sandbox subnet, so even a compromised API cannot use it to block
real hosts.

    uvicorn ovael.defense.agent:app --host 0.0.0.0 --port 9100
"""

from __future__ import annotations

import ipaddress
import os
import subprocess

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

SUBNET = ipaddress.ip_network(os.environ.get("OVAEL_SANDBOX_SUBNET", "172.28.0.0/16"))
TOKEN = os.environ.get("OVAEL_DEFENSE_TOKEN")
PROTECTED = {ip.strip() for ip in os.environ.get("OVAEL_DEFENSE_PROTECTED_IPS", "").split(",") if ip.strip()}
COMMENT = "ovael-auto-defense"

app = FastAPI(title="ovael defense agent", docs_url=None, redoc_url=None)


class Target(BaseModel):
    ip: str


def _auth(authorization: str | None = Header(default=None)) -> None:
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")


def _check(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(422, "not an IP address")
    if addr not in SUBNET:
        raise HTTPException(403, f"{ip} is outside the sandbox subnet {SUBNET}")
    if ip in PROTECTED:
        raise HTTPException(403, f"{ip} is protected")
    return str(addr)


def _rule(ip: str) -> list[str]:
    return ["INPUT", "-s", ip, "-j", "DROP", "-m", "comment", "--comment", COMMENT]


def _exists(ip: str) -> bool:
    return subprocess.run(["iptables", "-C", *_rule(ip)], capture_output=True).returncode == 0


@app.get("/health")
def health() -> dict:
    return {"ok": True, "subnet": str(SUBNET)}


@app.post("/block", dependencies=[Depends(_auth)])
def block(t: Target) -> dict:
    ip = _check(t.ip)
    if not _exists(ip):
        subprocess.run(["iptables", "-I", *_rule(ip)], check=True)
    return {"blocked": ip}


@app.post("/unblock", dependencies=[Depends(_auth)])
def unblock(t: Target) -> dict:
    ip = _check(t.ip)
    while _exists(ip):
        subprocess.run(["iptables", "-D", *_rule(ip)], check=True)
    return {"unblocked": ip}


@app.get("/rules", dependencies=[Depends(_auth)])
def rules() -> dict:
    out = subprocess.run(["iptables", "-S", "INPUT"], capture_output=True, text=True).stdout
    return {"rules": [line for line in out.splitlines() if COMMENT in line]}
