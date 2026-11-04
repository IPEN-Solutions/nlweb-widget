"""Command-line entry point for basic package diagnostics."""

import argparse


def main() -> None:
    """Run the package command-line interface."""
    parser = argparse.ArgumentParser(prog="nlweb-widget")
    parser.add_argument(
        "--version", action="store_true", help="show the package version"
    )
    args = parser.parse_args()
    if args.version:
        from . import __version__

        print(__version__)
    else:
        parser.print_help()
