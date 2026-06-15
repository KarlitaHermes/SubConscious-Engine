"""Entry point: python -m src"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.app import App
from src.config import CONFIG_ENV_VAR, load_config, resolve_config_path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SubConscious Engine")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to config YAML (default: ${CONFIG_ENV_VAR} or ~/.hermes/subconscious-engine/config.yaml)",
    )
    return parser


def main() -> None:
    """Load config and run the async application."""
    args = build_parser().parse_args()
    config_path = resolve_config_path(args.config)

    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Copy config.yaml.example to ~/.hermes/subconscious-engine/config.yaml "
            "or set SUBCONSCIOUS_CONFIG / pass --config",
            file=sys.stderr,
        )
        sys.exit(1)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = App(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
