"""JSON logs in production (one object per line, easy to ship), readable lines in development."""

from __future__ import annotations

import json
import logging
import os
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record), "level": record.levelname, "logger": record.name,
               "msg": record.getMessage()}
        if rid := getattr(record, "request_id", None):
            out["request_id"] = rid
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_ovael", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if os.environ.get("OVAEL_LOG_JSON", "").lower() in ("1", "true"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root.handlers = [handler]
    root.setLevel(level)
    root._ovael = True  # type: ignore[attr-defined]
    for noisy in ("uvicorn.access", "httpx", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
