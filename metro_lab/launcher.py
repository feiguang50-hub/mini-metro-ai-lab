from __future__ import annotations

import sys
from collections.abc import Callable

from .plugin_cli import consume_cli_plugins


def _configure_utf8_stdio() -> None:
    """Make the public CLIs reliable on Windows legacy console code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                # Some redirected or embedded streams cannot be reconfigured.
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


def _delegate_without_dynamic_plugins(main: Callable[[], None]) -> None:
    """Run a CLI that is not compatible with the dynamic simulator plugin contract."""

    _configure_utf8_stdio()
    main()


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

    _delegate_without_dynamic_plugins(main)
