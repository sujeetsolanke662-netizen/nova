"""Command-line entrypoint for NOVA Copilot.

    python -m backend.cli ask "<question>" [--root PATH]

This is the real entrypoint for the live demo - a `nova` shell
wrapper/alias around this can come later during packaging; don't build
that here, this module is the actual thing that runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app.copilot_answer import answer_query
from .app.copilot_retrieval import build_index
from .app.guardrails import load_protected_patterns
from .app.recommendation import generate_recommendations
from .config.settings import get_settings


def _run_ask(question: str, root_override: str | None) -> int:
    settings = get_settings()
    patterns = load_protected_patterns(settings.protected_paths_config)

    if root_override is not None:
        # An explicit --root is its own scan boundary for this invocation -
        # deliberately not required to be nested under settings.scan_roots,
        # so this can point at an arbitrary demo/test directory without
        # editing env vars first (that's the whole point of the flag).
        root = str(Path(root_override).expanduser())
        scan_roots = [root]
    else:
        if not settings.scan_roots:
            print(
                "No scan roots are configured - set NOVA_SCAN_ROOTS or pass --root.",
                file=sys.stderr,
            )
            return 1
        root = settings.scan_roots[0]
        scan_roots = settings.scan_roots

    if not Path(root).expanduser().is_dir():
        print(f"'{root}' is not an existing directory.", file=sys.stderr)
        return 1

    print("Scanning...")
    result = generate_recommendations(
        root, scan_roots, patterns, audit_log_path=settings.audit_log_path
    )
    recommendations = result["recommendations"]

    if not recommendations:
        print("Nothing to search - no files were found to scan under that root.")
        return 0

    index = build_index(recommendations)
    answer = answer_query(question, index)

    print()
    print(answer["answer_text"])

    if answer["cited_paths"]:
        print()
        print("Files referenced:")
        for path in answer["cited_paths"]:
            print(f"  - {path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova", description="NOVA Copilot CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask NOVA Copilot a question about your files")
    ask_parser.add_argument("question", help="The question to ask, in plain English")
    ask_parser.add_argument(
        "--root",
        default=None,
        help="Override the configured scan root for this invocation",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ask":
        return _run_ask(args.question, args.root)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
