from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .plugin_loader import LoadedPlugin, PluginLoadError, load_plugins


def add_plugin_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--plugin",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help="显式加载一个外部算法 .py 文件或目录；可重复使用",
    )


def preload_cli_plugins(argv: Sequence[str] | None = None) -> tuple[LoadedPlugin, ...]:
    """Load plugins before the full parser freezes algorithm choices."""

    pre_parser = argparse.ArgumentParser(add_help=False)
    add_plugin_argument(pre_parser)
    args, _unknown = pre_parser.parse_known_args(argv)
    try:
        return load_plugins(args.plugin)
    except PluginLoadError as exc:
        raise SystemExit(f"插件加载失败：{exc}") from exc
