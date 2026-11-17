import argparse
import json
from pathlib import Path
import subprocess
import sys

from .bundle import CheckpointError, dumps, export_checkpoint, prepare, verify
from .source import CodexSource


def main(argv=None):
    parser = argparse.ArgumentParser(description="Portable Codex conversation/workspace checkpoints")
    parser.add_argument("--codex", default="codex", help="Codex executable path")
    commands = parser.add_subparsers(dest="command", required=True)
    threads = commands.add_parser("threads")
    threads.add_subparsers(dest="threads_command", required=True).add_parser("list")
    export = commands.add_parser("export")
    source = export.add_mutually_exclusive_group(required=True)
    source.add_argument("--thread")
    source.add_argument("--source-json", type=Path, help="Previously collected {thread: {id, turns: [...]}} JSON")
    export.add_argument("--workspace", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--objective")
    export.add_argument("--next-action")
    for name in ("inspect", "verify", "prepare"):
        p = commands.add_parser(name)
        p.add_argument("checkpoint", type=Path)
        if name == "prepare":
            p.add_argument("--destination", type=Path, required=True)
            p.add_argument("--target", choices=["generic", "gemini-cli", "antigravity"], default="generic")
    args = parser.parse_args(argv)
    try:
        if args.command == "threads":
            with CodexSource(args.codex) as source:
                print(dumps(source.list_threads()), end="")
        elif args.command == "export":
            if args.source_json:
                data = json.loads(args.source_json.read_text())
            else:
                with CodexSource(args.codex) as source:
                    data = source.read_thread(args.thread)
            manifest = export_checkpoint(data, args.workspace, args.output, args.objective, args.next_action)
            print("Exported %s (%s events)" % (args.output, manifest["event_count"]))
        elif args.command == "prepare":
            prepare(args.checkpoint, args.destination, args.target)
            print("Restored %s; read BOOTSTRAP.md" % args.destination)
        else:
            manifest = verify(args.checkpoint)
            print(dumps(manifest) if args.command == "inspect" else "Verified %s files" % len(manifest["files"]), end="\n")
    except (CheckpointError, RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print("takeout: %s" % error, file=sys.stderr)
        return 1
    return 0
