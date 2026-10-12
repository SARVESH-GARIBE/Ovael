"""Command line: training, model management, schema setup.

    python -m ovael.cli train network|website|all [--force]
    python -m ovael.cli models [network|website]
    python -m ovael.cli promote <module> <version>
    python -m ovael.cli dataset check|import|info [capture.csv] [--source lab-1]
    python -m ovael.cli init-db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .config import get_settings
from .core.logging import setup_logging
from .ml.registry import ModelRegistry


def cmd_train(args) -> int:
    from .learning_loop.retrain import retrain

    s = get_settings()
    reg = ModelRegistry(s.model_dir)
    modules = ["network", "website"] if args.module == "all" else [args.module]
    for m in modules:
        if reg.active_version(m) and not args.force:
            print(f"{m}: {reg.active_version(m)} already active (use --force to train a new version)")
            continue
        res = retrain(m, s, reg, always_promote=args.force or reg.active_version(m) is None)
        print(json.dumps({k: res[k] for k in ("version", "promoted", "reason", "metrics")}, indent=2))
    return 0


def cmd_models(args) -> int:
    reg = ModelRegistry(get_settings().model_dir)
    for m in [args.module] if args.module else ["network", "website"]:
        for v in reg.list_versions(m):
            met = v.get("metrics", {})
            print(f"{v['version']:<14} {v['status']:<8} macro_f1={met.get('macro_f1')} "
                  f"label_source={v.get('label_source')} trained_at={v.get('trained_at')}")
    return 0


def cmd_promote(args) -> int:
    ModelRegistry(get_settings().model_dir).promote(args.module, args.version)
    print(f"{args.version} is now active")
    return 0


def cmd_dataset(args) -> int:
    from pathlib import Path

    import pandas as pd

    from .ml import dataset_tools

    s = get_settings()
    if args.action == "info":
        print(json.dumps(dataset_tools.info(s), indent=2))
        return 0
    if not args.csv:
        print("give the CSV to check or import")
        return 2
    if args.action == "check":
        report = dataset_tools.check(pd.read_csv(args.csv))
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    res = dataset_tools.import_csv(Path(args.csv), Path(s.network_dataset), args.source)
    print(json.dumps(res, indent=2))
    print("next: python -m ovael.cli train network --force")
    return 0


def cmd_init_db(_) -> int:
    from .db.session import Database

    async def run():
        db = Database(get_settings())
        await db.create_schema()
        await db.close()

    asyncio.run(run())
    print("schema created")
    return 0


def main(argv=None) -> int:
    setup_logging()
    logging.getLogger("ovael").setLevel(logging.INFO)
    p = argparse.ArgumentParser(prog="ovael")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("module", choices=["network", "website", "all"])
    t.add_argument("--force", action="store_true", help="train and promote a new version even if one is active")
    t.set_defaults(fn=cmd_train)
    m = sub.add_parser("models")
    m.add_argument("module", nargs="?", choices=["network", "website"])
    m.set_defaults(fn=cmd_models)
    pr = sub.add_parser("promote")
    pr.add_argument("module", choices=["network", "website"])
    pr.add_argument("version")
    pr.set_defaults(fn=cmd_promote)
    ds = sub.add_parser("dataset", help="check, import or describe recorded network datasets")
    ds.add_argument("action", choices=["check", "import", "info"])
    ds.add_argument("csv", nargs="?")
    ds.add_argument("--source", default="lab", help="tag stored with every imported row")
    ds.set_defaults(fn=cmd_dataset)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
