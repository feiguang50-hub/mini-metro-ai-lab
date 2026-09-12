from __future__ import annotations

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable

from .static_od import STATIC_ALGORITHMS, StaticAlgorithmRegistrationError, StaticAlgorithmMetadata


class StaticPluginLoadError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedStaticPlugin:
    path: Path
    metadata: StaticAlgorithmMetadata
    source_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_static_plugin_files(entry: Path) -> tuple[Path, ...]:
    path = Path(entry).expanduser().resolve()
    if path.is_file():
        if path.suffix.lower() != ".py":
            raise StaticPluginLoadError(f"static plugin file must end in .py: {path}")
        return (path,)
    if path.is_dir():
        files = tuple(
            candidate
            for candidate in sorted(path.glob("*.py"))
            if candidate.is_file() and not candidate.name.startswith("_")
        )
        if not files:
            raise StaticPluginLoadError(
                f"static plugin directory contains no visible top-level .py files: {path}"
            )
        return files
    raise StaticPluginLoadError(f"static plugin path does not exist: {path}")


def _load_module(path: Path) -> ModuleType:
    module_name = "mini_metro_static_external_" + hashlib.sha256(
        str(path).encode("utf-8")
    ).hexdigest()[:20]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StaticPluginLoadError(f"cannot create module spec for static plugin: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise StaticPluginLoadError(
            f"static plugin execution failed for {path.name}: {type(exc).__name__}: {exc}"
        ) from exc
    return module


def load_static_plugin_file(path: Path) -> LoadedStaticPlugin:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".py":
        raise StaticPluginLoadError(f"static plugin must be an existing .py file: {path}")
    module = _load_module(path)
    factory = getattr(module, "STATIC_PLUGIN_FACTORY", None)
    if not callable(factory):
        raise StaticPluginLoadError(
            f"static plugin {path.name} must expose callable STATIC_PLUGIN_FACTORY"
        )
    try:
        metadata = STATIC_ALGORITHMS.register(factory)
    except StaticAlgorithmRegistrationError as exc:
        raise StaticPluginLoadError(f"static plugin {path.name} rejected: {exc}") from exc
    except Exception as exc:
        raise StaticPluginLoadError(
            f"static plugin factory failed for {path.name}: {type(exc).__name__}: {exc}"
        ) from exc
    return LoadedStaticPlugin(path=path, metadata=metadata, source_sha256=_sha256(path))


def load_static_plugins(entries: Iterable[Path | str]) -> tuple[LoadedStaticPlugin, ...]:
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in entries:
        for path in discover_static_plugin_files(Path(raw)):
            if path not in seen:
                seen.add(path)
                files.append(path)
    return tuple(load_static_plugin_file(path) for path in files)
