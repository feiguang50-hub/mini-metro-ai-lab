from __future__ import annotations

import sys
from collections.abc import Callable

from .plugin_cli import consume_cli_plugins


def _delegate(main: Callable[[], None]) -> None:
    _loaded, remaining = consume_cli_plugins(sys.argv[1:])
    original = sys.argv
    sys.argv = [original[0], *remaining]
    try:
        main()
    finally:
        sys.argv = original


def server_main() -> None:
    from .server import main

    _delegate(main)


def arena_main() -> None:
    from .arena import main

    _delegate(main)


def battle_main() -> None:
    from .battle import main

    _delegate(main)
