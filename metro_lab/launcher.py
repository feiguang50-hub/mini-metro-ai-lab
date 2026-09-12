from __future__ import annotations

import sys
from collections.abc import Callable

from .plugin_cli import consume_cli_plugins
from .static_plugin_cli import consume_static_cli_plugins


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _delegate(main: Callable[[], None]) -> None:
    _configure_utf8_stdio()
    _loaded, remaining = consume_cli_plugins(sys.argv[1:])
    original = sys.argv
    sys.argv = [original[0], *remaining]
    try:
        main()
    finally:
        sys.argv = original


def _delegate_static(main: Callable[[], None]) -> None:
    _configure_utf8_stdio()
    _loaded, remaining = consume_static_cli_plugins(sys.argv[1:])
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


def static_od_main() -> None:
    from .static_od import main
    _delegate_static(main)


def static_infra_main() -> None:
    from .static_infra import main
    _delegate_static(main)


def static_uncertainty_main() -> None:
    from .static_uncertain import main
    _delegate_static(main)
