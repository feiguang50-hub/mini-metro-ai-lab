from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / ".vendor"
ENGINE_ROOT = VENDOR_ROOT / "python_mini_metro"
ENGINE_SRC = ENGINE_ROOT / "src"
WEB_ROOT = ROOT / "web"

ENGINE_REPOSITORY = "https://github.com/yanfengliu/python_mini_metro.git"
ENGINE_COMMIT = "382d7cc65da566ac01d8151921c203c25418eacd"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_SEED = 42
TICK_MS = 100
