"""The normative VS-001 CLI. All structured output is JSON."""

import argparse
from pathlib import Path
import sqlite3
import sys

from arf.models import ARFError, Charter, TaskSpec, json_text, parse_json
from arf.service import recover, run_next
from arf.store import Store


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m arf", description="Fixed local demo lifecycle (VS-001)")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--db", required=True)
    init.add_argument("--charter", required=True)
    task = commands.add_parser("task").add_subparsers(dest="action", required=True)
    for name in ("add", "list", "show", "retry"):
        child = task.add_parser(name)
        child.add_argument("--db", required=True)
        if name == "add":
            child.add_argument("--spec", required=True)
        if name in ("show", "retry"):
            child.add_argument("--id", required=True)
    for name in ("run-next", "recover"):
        commands.add_parser(name).add_argument("--db", required=True)
    evidence = commands.add_parser("evidence").add_subparsers(dest="action", required=True)
    evidence.add_parser("list").add_argument("--db", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        # Validate file imports before creating or modifying a database.
        charter = Charter.parse(Path(args.charter).read_bytes()) if args.command == "init" else None
        spec = (
            TaskSpec.parse(parse_json(Path(args.spec).read_bytes()))
            if args.command == "task" and args.action == "add" else None
        )
        with Store(args.db, create=args.command == "init") as store:
            if args.command == "init":
                output = store.import_charter(charter)
            elif args.command == "task":
                if args.action == "add":
                    output = store.add_task(spec)
                elif args.action == "list":
                    output = store.tasks()
                elif args.action == "show":
                    output = store.task(args.id)
                else:
                    output = store.retry(args.id)
            elif args.command == "run-next":
                output = run_next(store)
            elif args.command == "recover":
                output = recover(store)
            else:
                output = store.evidence()
        print(json_text(output))
        return 1 if isinstance(output, dict) and output.get("status") == "failed" else 0
    except (ARFError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: controller interrupted; inspect the database and use recover", file=sys.stderr)
        return 130
