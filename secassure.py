#!/usr/bin/env python3
"""AssureBench CLI entry point."""

import argparse
from pathlib import Path

import server


def main():
    parser = argparse.ArgumentParser(
        description="Scan a local repository and write the AssureBench Markdown report to stdout."
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=Path("."),
        help="repository directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="write the Markdown report to this file instead of stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="also stream scanner logs to stderr",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="start the local browser dashboard instead of scanning",
    )
    parser.add_argument(
        "--container",
        action="store_true",
        help="use the private Docker work volume (for running the CLI in a container)",
    )
    args = parser.parse_args()
    if args.dashboard:
        if args.output or args.verbose:
            parser.error("--output and --verbose are only available when scanning")
        if args.container:
            server.enable_container_runtime()
        return server.run_dashboard()
    if args.container:
        server.enable_container_runtime()
    return server.run_cli_scan(args.project, args.output, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
