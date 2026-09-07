from __future__ import annotations

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable

from .algorithms import AlgorithmSpec, register_external_algorithm
from .plugin import AlgorithmFactory, PluginRegistrationError


class PluginLoadError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedPlugin:
    path: Path
    spec: AlgorithmSpec


def _entry_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_plugin_files(entry: Path) -> tuple[Path, ...]:
    """Expand one explicitly supplied file or directory into plugin files.

    Directories are shallow by design: every visible top-level ``*.py`` file is
    treated as one plugin entry. This avoids surprising recursive execution of
    arbitrary Python files nested under helper/source trees.
    """

    path = Path(entry).expanduser().resolve()
    if path.is_file():
        if path.suffix.lower() != ".py":
            raise PluginLoadError(f"plugin file must end in .py: {path}")
        return (path,)
    if path.is_dir():
        files = tuple(
            candidate
            for candidate in sorted(path.glob("*.py"))
            if candidate.is_file() and not candidate.name.startswith("_")
        )
        if not files:
            raise PluginLoadError(
                f"plugin directory contains no visible top-level .py files: {path}"
            )
        return files
    raise PluginLoadError(f"plugin path does not exist: {path}")


def _load_module(path: Path) -> ModuleType:
    module_name = "mini_metro_external_" + hashlib.sha256(
        str(path).encode("utf-8")
    ).hexdigest()[:20]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot create module spec for plugin: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise PluginLoadError(
            f"plugin execution failed for {path.name}: {type(exc).__name__}: {exc}"
        ) from exc
    return module


def load_plugin_file(path: Path) -> LoadedPlugin:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".py":
        raise PluginLoadError(f"plugin must be an existing .py file: {path}")

    module = _load_module(path)
    factory = getattr(module, "PLUGIN_FACTORY", None)
    if not callable(factory):
        raise PluginLoadError(
            f"plugin {path.name} must expose callable PLUGIN_FACTORY"
        )

    try:
        algorithm_spec = register_external_algorithm(
            factory,
            source_name=path.name,
            source_sha256=_entry_sha256(path),
        )
    except PluginRegistrationError as exc:
        raise PluginLoadError(f"plugin {path.name} rejected: {exc}") from exc
    except Exception as exc:
        raise PluginLoadError(
            f"plugin factory failed for {path.name}: {type(exc).__name__}: {exc}"
        ) from exc

    return LoadedPlugin(path=path, spec=algorithm_spec)


def load_plugins(entries: Iterable[Path | str]) -> tuple[LoadedPlugin, ...]:
    """Load explicitly opted-in plugin files/directories in deterministic order."""

    files: list[Path] = []
    seen: set[Path] = set()
    for raw in entries:
        for path in discover_plugin_files(Path(raw)):
            if path not in seen:
                seen.add(path)
                files.append(path)

    loaded: list[LoadedPlugin] = []
    for path in files:
        loaded.append(load_plugin_file(path))
    return tuple(loaded)
