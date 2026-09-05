#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$ROOT/.vendor/python_mini_metro"
ENGINE_REPO="https://github.com/yanfengliu/python_mini_metro.git"
ENGINE_COMMIT="382d7cc65da566ac01d8151921c203c25418eacd"

if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<'MSG'
未找到 uv。请先安装：
  curl -LsSf https://astral.sh/uv/install.sh | sh
然后重新运行 ./run.sh
MSG
  exit 1
fi

mkdir -p "$ROOT/.vendor"

if [[ ! -d "$ENGINE_DIR/.git" ]]; then
  echo "→ 下载 Mini Metro 引擎…"
  rm -rf "$ENGINE_DIR"
  git clone --filter=blob:none --no-checkout "$ENGINE_REPO" "$ENGINE_DIR"
fi

printf '→ 固定引擎版本 %s…\n' "${ENGINE_COMMIT:0:12}"
git -C "$ENGINE_DIR" fetch --depth 1 origin "$ENGINE_COMMIT"
git -C "$ENGINE_DIR" checkout --detach --force "$ENGINE_COMMIT" >/dev/null

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "→ 创建 Python 3.13 环境…"
  uv python install 3.13
  uv venv --python 3.13 "$ROOT/.venv"
fi

echo "→ 安装引擎依赖…"
uv pip install --python "$ROOT/.venv/bin/python" -r "$ENGINE_DIR/requirements-locked.txt"

echo "→ 安装 Mini Metro Lab…"
uv pip install --python "$ROOT/.venv/bin/python" -e "$ROOT"

echo "✓ 环境准备完成"
