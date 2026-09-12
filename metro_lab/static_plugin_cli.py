from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .static_plugin_loader import LoadedStaticPlugin, load_static_plugins


def consume_static_cli_plugins(argv: Iterable[str]) -> tuple[tuple[LoadedStaticPlugin, ...], list[str]]:
    """Consume repeated --plugin PATH options before the Static OD parser runs."""

    args = list(argv)
    entries: list[Path] = []
    remaining: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--plugin":
            if index + 1 >= len(args):
                raise SystemExit("--plugin requires a file or directory path")
            entries.append(Path(args[index + 1]))
            index += 2
            continue
        if token.startswith("--plugin="):
            value = token.split("=", 1)[1]
            if not value:
                raise SystemExit("--plugin requires a file or directory path")
            entries.append(Path(value))
            index += 1
            continue
        remaining.append(token)
        index += 1

    return load_static_plugins(entries), remaining
