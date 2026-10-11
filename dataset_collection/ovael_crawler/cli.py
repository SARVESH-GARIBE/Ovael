"""Command line entry point: python -m ovael_crawler <command> ..."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

from . import SCHEMA_VERSION, config
from .config import CrawlConfig
from .domains import PSL_SOURCE
from .reference import (TrackerReference, fetch_tds, fetch_urlhaus, identify_tranco, load_json, utcnow)
from .selection import SELECTION_METHOD, select_list, select_tranco

PROJECT = "AI-Based Website Behavioral Analysis and Tracker Detection System"


def _out(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else config.COLLECTION_DIR / path


def cmd_fetch_references(args) -> int:
    print("Downloading DuckDuckGo Tracker Data Set ...")
    print(json.dumps(fetch_tds(), indent=2))
    print("Downloading URLhaus malware host list ...")
    try:
        print(json.dumps(fetch_urlhaus(), indent=2))
    except Exception as e:
        print(f"WARNING: URLhaus download failed ({e!r}); selection will record that no malware-list check was done")
    print("Identifying Tranco list ...")
    meta = identify_tranco(Path(args.tranco_csv))
    print(json.dumps({k: meta.get(k) for k in ("list_id", "verified", "list_date", "candidates_checked")}, indent=2))
    return 0


def _base_manifest(run_type: str, selected: list, skipped: list, urlhaus_used: bool, source: dict, n: int | None) -> dict:
    ref = TrackerReference()
    return {
        "schema_version": SCHEMA_VERSION, "project": PROJECT, "run_type": run_type, "created_at": utcnow(),
        "source": source,
        "selection": {"method": SELECTION_METHOD if run_type == "tranco" else
                      "Smoke-test list (smoke_sites.txt) in file order, de-duplicated by registrable domain.",
                      "requested": n, "selected_count": len(selected), "skipped_count": len(skipped),
                      "skipped": skipped, "public_suffix_list": PSL_SOURCE,
                      "malware_host_check": ({"source": "URLhaus hostfile (abuse.ch)", **(load_json(config.URLHAUS_META_PATH) or {})}
                                             if urlhaus_used else "not performed: URLhaus list unavailable")},
        "reference": ref.version,
        "crawl_config": CrawlConfig().to_dict(),
        "selected": selected,
        "status": {"selected": len(selected), "attempted": 0, "completed_observed": 0, "success": 0,
                   "http_error": 0, "failed": 0, "blocked_unsafe": 0, "pending": len(selected), "complete": False},
        "runs": [],
    }


def _guard_new(out: Path, force: bool) -> None:
    if (out / "website_observations.jsonl").exists() and not force:
        raise SystemExit(f"{out} already contains crawl records; refusing to re-select. "
                         f"Use a new --output directory (or --force to replace the selection only).")
    out.mkdir(parents=True, exist_ok=True)


def cmd_select(args) -> int:
    out = _out(args.output)
    _guard_new(out, args.force)
    tranco = load_json(config.TRANCO_META_PATH)
    if not tranco or tranco.get("source_file") != Path(args.tranco_csv).name:
        tranco = identify_tranco(Path(args.tranco_csv))
    selected, skipped, urlhaus_used = select_tranco(Path(args.tranco_csv), args.n)
    if len(selected) != args.n:
        raise SystemExit(f"only {len(selected)} eligible domains found")
    source = {"type": "Tranco", **tranco,
              "download_date": (tranco.get("list_created_on") or tranco.get("source_file_mtime_utc"))}
    m = _base_manifest("tranco", selected, skipped, urlhaus_used, source, args.n)
    (out / "crawl_manifest.json").write_text(json.dumps(m, indent=2))
    print(f"Selected {len(selected)} unique registrable domains (skipped {len(skipped)} entries) -> {out}/crawl_manifest.json")
    return 0


def _config_from(args) -> CrawlConfig:
    cfg = CrawlConfig()
    for name in ("workers", "settle_s", "navigation_timeout_s", "overall_timeout_s", "max_retries", "load_event_timeout_s"):
        v = getattr(args, name, None)
        if v is not None:
            setattr(cfg, name, v)
    if getattr(args, "headed", False):
        cfg.headless = False
    return cfg


def cmd_crawl(args) -> int:
    from .crawler import run_crawl
    out = _out(args.output)
    status = asyncio.run(run_crawl(out, _config_from(args), limit=args.limit))
    if not args.no_report:
        from .report import build_report
        build_report(out)
    return 0 if status["complete"] or args.limit else 2


def cmd_smoke(args) -> int:
    from .crawler import run_crawl
    from .report import build_report
    from .validate import validate
    out = _out(args.output)
    if not args.resume:
        _guard_new(out, args.force)
        if args.force:
            for f in out.glob("*"):
                if f.is_file():
                    f.unlink()
        selected, skipped, urlhaus_used = select_list(config.SMOKE_SITES)
        source = {"type": "smoke-test list", "source_file": config.SMOKE_SITES.name}
        m = _base_manifest("smoke", selected, skipped, urlhaus_used, source, None)
        (out / "crawl_manifest.json").write_text(json.dumps(m, indent=2))
        print(f"Smoke list: {len(selected)} entries selected, {len(skipped)} skipped: {skipped}")
    fd, audit = tempfile.mkstemp(prefix="ovael-cookie-audit-", dir=os.environ.get("TMPDIR"))
    os.close(fd)
    audit_path = Path(audit)
    try:
        from .selftest import run_selftest
        self_ok = run_selftest()
        asyncio.run(run_crawl(out, _config_from(args), limit=args.limit, secret_audit=audit_path))
        build_report(out)
        ok = validate(out, secret_audit=audit_path) and self_ok
    finally:
        audit_path.unlink(missing_ok=True)  # real cookie values never persist
    return 0 if ok else 1


def cmd_report(args) -> int:
    from .report import build_report
    print(f"Wrote {build_report(_out(args.output))}")
    return 0


def cmd_validate(args) -> int:
    from .validate import validate
    return 0 if validate(_out(args.output)) else 1


def cmd_selftest(args) -> int:
    from .selftest import run_selftest
    return 0 if run_selftest() else 1


def cmd_status(args) -> int:
    from .crawler import OutputStore, status_counts
    out = _out(args.output)
    m = json.loads((out / "crawl_manifest.json").read_text())
    ref = TrackerReference()
    recs = OutputStore(out, ref.categories, ref.version).load_records()
    print(json.dumps(status_counts(m, recs), indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m ovael_crawler", description=PROJECT + " - data collection")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch-references", help="download tracker list + malware host list, identify Tranco list")
    s.add_argument("--tranco-csv", default=str(config.DEFAULT_TRANCO_CSV))
    s.set_defaults(fn=cmd_fetch_references)

    s = sub.add_parser("select", help="select N unique domains from the Tranco list")
    s.add_argument("--n", type=int, default=500)
    s.add_argument("--tranco-csv", default=str(config.DEFAULT_TRANCO_CSV))
    s.add_argument("--output", default="output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_select)

    def crawl_opts(s):
        s.add_argument("--workers", type=int)
        s.add_argument("--settle-s", dest="settle_s", type=float)
        s.add_argument("--navigation-timeout-s", dest="navigation_timeout_s", type=float)
        s.add_argument("--load-event-timeout-s", dest="load_event_timeout_s", type=float)
        s.add_argument("--overall-timeout-s", dest="overall_timeout_s", type=float)
        s.add_argument("--max-retries", dest="max_retries", type=int)
        s.add_argument("--limit", type=int, help="visit at most this many pending websites in this run")
        s.add_argument("--headed", action="store_true")

    s = sub.add_parser("crawl", help="crawl (or resume) the selection in --output")
    s.add_argument("--output", default="output")
    s.add_argument("--no-report", action="store_true")
    crawl_opts(s)
    s.set_defaults(fn=cmd_crawl)

    s = sub.add_parser("smoke", help="smoke test on smoke_sites.txt, then validate outputs")
    s.add_argument("--output", default="output_smoke")
    s.add_argument("--resume", action="store_true")
    s.add_argument("--force", action="store_true", help="delete previous smoke outputs first")
    crawl_opts(s)
    s.set_defaults(fn=cmd_smoke)

    for name, fn, h in (("report", cmd_report, "regenerate dataset_documentation.docx"),
                        ("validate", cmd_validate, "check output consistency and privacy"),
                        ("status", cmd_status, "print selected/attempted/completed/failed/pending")):
        s = sub.add_parser(name, help=h)
        s.add_argument("--output", default="output")
        s.set_defaults(fn=fn)

    s = sub.add_parser("selftest", help="offline check that the API instrumentation counts correctly")
    s.set_defaults(fn=cmd_selftest)

    args = p.parse_args(argv)
    return args.fn(args)
