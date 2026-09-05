# 🚇 Mini Metro AI Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与策略进化** 的本地实验场。

它固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证版本作为底层模拟器，在上面提供：

- 🇨🇳 **全中文观战界面**：浏览器实时看线路、车站、列车和客流变化。
- 🧠 **可选择算法库**：已经实现的算法可以直接切换；规划中的算法显示开发状态。
- 🏁 **固定 Seed Arena**：同 Seeds、同步长、同预算比较算法。
- ⚔️ **同 Seed 同步 Battle**：两个独立环境逐步同步推进，直接进行算法对战。
- 📼 **实验档案与回放**：保存配置、结果、CSV、摘要和压缩回放流。
- 👀 **沉浸观战**：地图是主角，AI 信息可以隐藏。
- 🔒 **完全本地运行**：默认只监听 `127.0.0.1`，不需要 OpenAI API，也不上传游戏状态。
- 🧹 **干净安装**：依赖只在项目目录的 `.venv` 和 `.vendor` 中。

> 当前版本：**0.6.0 / Synchronized Battle + Balanced Greedy V2 Candidate**。

## 30 秒启动

需要 Linux、Git、[`uv`](https://docs.astral.sh/uv/) 和能访问 GitHub 的网络。

```bash
./run.sh
```

第一次运行会自动下载固定版本引擎、创建 Python 3.13 项目环境、安装依赖并打开本地观战页。

默认地址：<http://127.0.0.1:8765>

## 🗃️ 算法库

当前真正可运行的算法有两个：

| ID | 算法 | 状态 | 说明 |
| --- | --- | --- | --- |
| `greedy-v1` | Greedy Planner V1 | `baseline` | 几何距离 + 即时拥堵的透明基线，仍是默认算法 |
| `balanced-greedy-v2` | Balanced Greedy V2 | `candidate` | 同时考虑站型、线路长度、压力与分流机会 |

规划中但尚不可运行：

- Beam Search
- Model Predictive Control (MPC)
- Monte Carlo Tree Search (MCTS)
- Policy + Value + Search
- Recurrent PPO

观战页右侧算法库直接读取 `metro_lab/algorithms.py`。切换算法会**保持当前 Seed 并自动重开**，方便肉眼公平比较。

命令行也可以直接指定：

```bash
./run.sh --algorithm balanced-greedy-v2
```

### Balanced Greedy V2 首战

固定 Seeds `42, 314, 2026, 4096, 65537`，每局 15 分钟：

| 指标 | Greedy V1 | Balanced V2 |
| --- | ---: | ---: |
| 平均运送量 | 38.40 | **38.80** |
| 中位数 | 38.00 | 38.00 |
| 最低 / 最高 | 35 / 42 | 35 / 42 |
| Game Over 率 | 0% | 0% |
| 无效动作 | 21 | **16** |

V2 平均只提高约 1%，还不足以晋升冠军，所以 **V1 保持默认 baseline，V2 只作为 candidate 开放**。完整记录见 [`docs/algorithm-history.md`](docs/algorithm-history.md)。

## 👀 观战模式

地图 HUD：

- **客流**：显示 / 隐藏站台乘客目标形状。
- **沉浸观战**：隐藏 AI 侧栏，让地图占满可用宽度。

底部控制：

- 暂停 / 继续
- 1× / 2× / 4×
- 同 Seed 重开
- 随机新局

按 `Ctrl+C` 关闭服务。

## 🏁 Arena

第一次运行过 `./run.sh` 后：

```bash
.venv/bin/mini-metro-arena
```

常用例子：

```bash
# V1 与 V2 在相同 Seeds 下比较
.venv/bin/mini-metro-arena \
  --algorithms greedy-v1 balanced-greedy-v2 \
  --seeds 42 314 2026 4096 65537 \
  --minutes 15

# 机器可读输出
.venv/bin/mini-metro-arena --json

# 只跑，不保存实验文件
.venv/bin/mini-metro-arena --no-save
```

当前排行榜指标包括平均值、中位数、最低 / 最高运送量、Game Over 率和无效动作数。

## ⚔️ 同 Seed 同步 Battle

Battle 不是把两个算法顺序跑一遍，而是创建两个**完全独立**的 `MiniMetroEnv`，使用相同 Seed、相同 `dt_ms` 和相同预算逐轮同步推进。一侧提前 Game Over 后会冻结，另一侧继续到结束或预算耗尽。

```bash
.venv/bin/mini-metro-battle \
  greedy-v1 balanced-greedy-v2 \
  --seed 42 \
  --minutes 15
```

需要双方回放：

```bash
.venv/bin/mini-metro-battle \
  greedy-v1 balanced-greedy-v2 \
  --seed 42 \
  --minutes 15 \
  --replays
```

公平性有真实引擎回归测试：**同算法 + 同 Seed 必须得到完全相同的双方结果并严格平局**。这用来防止共享随机状态或执行顺序污染制造“假优势”。

## 📼 实验档案与回放

Arena 默认把实验保存到：

```text
output/experiments/<timestamp>-<algorithm...>/
```

典型结构：

```text
config.json
results.json
episodes.csv
summary.md
replays/
  *.jsonl.gz
```

回放流记录：

- 开局状态；
- 周期性结构化状态采样；
- 所有非 `noop` 决策；
- Game Over 最终状态；
- 算法、Seed、步长、时间预算、引擎提交。

常用选项：

```bash
.venv/bin/mini-metro-arena --no-replays
.venv/bin/mini-metro-arena --no-save
.venv/bin/mini-metro-arena --replay-sample-ms 500
```

`output/` 已被 Git 忽略。普通跑分不进入仓库，只有有研究价值的代表性实验才会晋升为长期记录。

## 实验纪律

- 同轮比较必须使用相同 Seeds、步长和时间预算；
- 小样本只能算候选证据；
- 新冠军必须明确击败当前基线 / 冠军；
- 失败和被淘汰算法保留历史，不抹掉研究记忆；
- 结果必须能追溯到算法版本和引擎版本；
- “看起来聪明”不算赢，数据不过关就不升默认。

## 架构

```text
                     Algorithm Library
                           │
                    algorithms.py
                      │         │
                      ▼         ▼
                  LabRuntime   Arena
                      │         │
                      │      Experiments / Replay
                      │
                      ├──────────────┐
                      ▼              ▼
                 MiniMetroEnv   Synchronized Battle
                                   │       │
                                   ▼       ▼
                              MiniMetroEnv MiniMetroEnv
                                   same Seed / same dt
```

## 项目结构

```text
metro_lab/
  algorithms.py          # 算法注册表
  planner.py             # Greedy Planner V1
  balanced_planner.py    # Balanced Greedy V2
  engine.py              # 实时模拟运行时
  arena.py               # 固定 Seed 竞技场
  battle.py              # 同 Seed 同步双算法对战
  experiments.py         # 实验产物与 ReplayWriter
  server.py              # 本地 HTTP API
web/
  index.html
  styles.css
  algorithm-library.css
  app.js
docs/
  algorithm-history.md
tests/
  test_algorithm_library.py
  test_planner.py
  test_balanced_planner.py
  test_battle.py
  test_engine_smoke.py
  test_arena.py
  test_experiments.py
  test_web_contract.py
```

## 固定上游版本

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`，不会静默追随上游 `main`。

## 测试与 CI

GitHub Actions 会真实执行：

1. Shell 语法检查；
2. 下载并固定上游 Mini Metro 引擎；
3. Python 编译；
4. Algorithm Library / Planner / Battle / Arena / Experiments / Web 测试；
5. 真实引擎 smoke test；
6. 同算法同 Seed 严格平局测试；
7. V1 vs V2 固定 Seeds、15 分钟候选 benchmark；
8. 启动 HTTP 观战服务并请求 `/api/state`。

## 清理

```bash
./scripts/clean.sh
```

彻底卸载直接删除仓库目录即可，不修改系统 Python。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本仓库新增代码同样采用 MIT License。
