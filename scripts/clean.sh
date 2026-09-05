#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -rf "$ROOT/.venv" "$ROOT/.vendor" "$ROOT/output"
echo "✓ 已删除 .venv、.vendor 和 output；源码保持不变。"
