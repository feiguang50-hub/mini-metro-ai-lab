# 🚇 Mini Metro AI Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与策略进化** 的本地实验场。

它固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证版本作为底层模拟器，在上面提供：

- 🇨🇳 **全中文观战界面**：浏览器实时看线路、车站、列车和客流变化。
- 🧠 **可选择算法库**：已经实现的算法可以直接切换；规划中的算法显示开发状态。
- 🏁 **固定 Seed Arena**：同 Seeds、同步长、同预算、同 Simulation Protocol 比较算法。
- ⚔️ **同 Seed 同步 Battle**：两个独立环境逐步同步推进，直接进行算法对战。
- 📊 **Arena V2 健康指标**：不仅看运送量，还测候车、拥堵、载客率和动作稳定性。
- 📼 **实验档案与回放**：保存配置、结果、CSV、摘要和压缩回放流。
- 👀 **沉浸观战**：地图是主角，AI 信息可以隐藏。
- 🔒 **完全本地运行**：默认只监听 `127.0.0.1`，不需要 OpenAI API，也不上传游戏状态。
- 🧹 **干净安装**：依赖只在项目目录的 `.venv` 和 `.vendor` 中。

> 当前版本：**0.7.0 / Arena V2 + Simulation Protocol V2**。

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

最初的 0.6.x / Protocol V1 实验使用固定 Seeds `42, 314, 2026, 4096, 65537`，每局名义预算 15 分钟：

| 指标 | Greedy V1 | Balanced V2 |
| --- | ---: | ---: |
| 平均运送量 | 38.40 | **38.80** |
| 中位数 | 38.00 | 38.00 |
| 最低 / 最高 | 35 / 42 | 35 / 42 |
| Game Over 率 | 0% | 0% |
| 无效动作 | 21 | **16** |

V2 平均只提高约 1%，还不足以晋升冠军，所以 **V1 保持默认 baseline，V2 只作为 candidate 开放**。完整版本化记录见 [`docs/algorithm-history.md`](docs/algorithm-history.md)。

## 👀 观战模式

地图 HUD：

- **客流**：显示 / 隐藏站台乘客目标形状。
- **沉浸观战**：隐藏 AI 侧栏，让地图占满可用宽度。
- **动态站点**：浏览器观战从固定 Seed 的站点池中按模拟时间逐步开放新站，避免画面长期停在少量站点。

底部控制：

- 暂停 / 继续
- 1× / 2× / 4×
- 同 Seed 重开
- 随机新局

按 `Ctrl+C` 关闭服务。

## 🏁 Arena V2

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

Arena V2 记录的不再只有最终分数：

- 运送量、`deliveries/min`
- 实际生存 / 模拟时间
- **时间加权平均候车人数**
- passenger waiting seconds
- 全网候车峰值
- 单站最大候车队列
- **时间加权车队载客率**
- 最大线路、站点、机车、车厢规模
- 非 `noop` 动作数、拓扑修改数
- 无效动作数与 invalid action rate
- Game Over 率

排行榜仍以运送量作为主排序，不偷偷发明一个难解释的“综合神分”。健康指标用于解释算法为什么赢、网络是不是已经变成毛线团，以及同分方案谁更稳。

### Simulation Protocol V2

固定步长公平性从 0.7.0 起成为显式协议：

1. planner 每轮提交一个动作；
2. 若动作有效，正常推进固定 `dt`；
3. 若动作被底层引擎拒绝，仍记录为 invalid，但随后用 `noop` 消耗这一轮相同的 `dt`；
4. 除非 Game Over，固定 15 分钟预算就必须真的经历完整 15 分钟城市时间。

这是因为固定的上游引擎有一个重要语义：**被拒绝的动作本身不走时**。Protocol V1 的 Arena 因此可能出现 14.98 分钟这种小偏差。旧结果不会被删除或改写，只会保留 `Protocol V1` 标签；新实验默认使用 V2。

Arena、CLI Battle 和浏览器 Battle 从 0.7.0 起共用同一个 `advance_fixed_dt()` 实现，避免三个入口悄悄长出三套比赛规则。

## ⚔️ 同 Seed 同步 Battle

Battle 不是把两个算法顺序跑一遍，而是创建两个**完全独立**的 `MiniMetroEnv`，使用相同 Seed、相同 `dt_ms`、相同预算和相同 Simulation Protocol 逐轮同步推进。一侧提前 Game Over 后会冻结，另一侧继续到结束或预算耗尽。

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

## 🌆 Benchmark 场景与浏览器场景

目前有意保留两种不同用途：

- **Classic benchmark**：Arena / CLI Battle 沿用上游原始站点推进逻辑，保证旧实验可追溯、可版本化比较。
- **Viewer timed progression**：单算法和浏览器双算法观战从开局 3 站开始，每 45 秒模拟时间增加一个新站，最多 20 站，让观战过程持续产生新问题。

两者不会偷偷混用。0.7.0 的新指标还揭示：Classic 15 分钟在当前固定 Seeds 上压力偏低，单站峰值只有约 1。后续会新增**显式版本化的 Stress Scenario**，而不是直接篡改 Classic 规则，让更强算法真正有地方拉开差距。

## 🌐 浏览器双算法 Battle

启动 `./run.sh` 后，从观战室点击「进入双算法对战」，或打开本地 `/battle.html`。

- 从算法库分别选择左右算法；尚未实现的算法不可选。
- 左右共享相同 Seed、步长、预算和动态站点时间表。
- 顶部显示运送比分、领先人数、对战状态；每侧显示拥堵风险、运行状态和最新决策。
- 「开始新对战」应用表单配置；「原配置重开」使用上次已提交配置。
- 服务端逐轮推进两个独立环境，并原子发布同一轮双方快照。浏览器刷新和多开页面不会增加模拟步数。
- 一侧 Game Over 后冻结，另一侧继续至共同预算；双方均结束则提前停止。
- 当前服务共用一个 Battle 会话；其他浏览器开始新局会替换该会话。单算法会话独立运行。

API：

- `GET /api/battle/state`
- `POST /api/battle/control`

开始示例：

```json
{
  "command": "start",
  "value": {
    "left": "greedy-v1",
    "right": "balanced-greedy-v2",
    "seed": 42,
    "dt_ms": 100,
    "budget_ms": 900000
  }
}
```

Seed 范围 `0..2147483647`、步长 `10..1000 ms`、预算 `100..3600000 ms`，预算须为步长的整数倍。

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

从 Protocol V2 起，实验配置、结果和 Replay header 都显式记录 `simulation_protocol`。回放流还记录：

- 开局状态
- 周期性结构化状态采样
- 所有非 `noop` 决策
- Game Over 最终状态
- 算法、Seed、步长、时间预算、引擎提交

常用选项：

```bash
.venv/bin/mini-metro-arena --no-replays
.venv/bin/mini-metro-arena --no-save
.venv/bin/mini-metro-arena --replay-sample-ms 500
```

`output/` 已被 Git 忽略。普通跑分不进入仓库，只有有研究价值的代表性实验才会晋升为长期记录。

## 实验纪律

- 同轮比较必须使用相同 Seeds、步长、时间预算、场景和 Simulation Protocol；
- 小样本只能算候选证据；
- 新冠军必须明确击败当前基线 / 冠军；
- 失败和被淘汰算法保留历史，不抹掉研究记忆；
- 协议升级不重写旧结果，而是追加新口径实验；
- 结果必须能追溯到算法、引擎、场景和协议版本；
- “看起来聪明”不算赢，数据不过关就不升默认。

## 架构

```text
                     Algorithm Library
                           │
                    algorithms.py
                      │         │
                      ▼         ▼
                  LabRuntime   Arena V2
                      │         │
                      │     Metrics / Experiments / Replay
                      │         │
                      ├─────────┴─────────────┐
                      ▼                       ▼
                 MiniMetroEnv           Simulation Protocol V2
                                              │
                                  ┌───────────┴───────────┐
                                  ▼                       ▼
                              CLI Battle             Live Battle
                                  │                       │
                                  ▼                       ▼
                             MiniMetroEnv             MiniMetroEnv × 2
```

## 项目结构

```text
metro_lab/
  algorithms.py          # 算法注册表
  planner.py             # Greedy Planner V1
  balanced_planner.py    # Balanced Greedy V2
  simulation.py          # 固定 dt 的 Simulation Protocol V2
  metrics.py             # Arena V2 时间加权健康指标
  engine.py              # 单算法实时模拟运行时
  arena.py               # 固定 Seed Arena V2
  battle.py              # CLI 同 Seed 同步双算法对战
  live_battle.py         # 浏览器双算法原子同步运行时
  viewer_scenario.py     # 浏览器动态站点场景
  experiments.py         # 实验产物与 ReplayWriter
  server.py              # 本地 HTTP API
web/
  index.html
  battle.html
  styles.css
  battle.css
  algorithm-library.css
  app.js
  battle.js
  map-renderer.js
docs/
  algorithm-history.md
tests/
  test_simulation.py
  test_metrics.py
  test_algorithm_library.py
  test_planner.py
  test_balanced_planner.py
  test_battle.py
  test_live_battle.py
  test_engine_smoke.py
  test_arena.py
  test_experiments.py
  test_viewer_scenario.py
  test_web_contract.py
  web_battle.cjs
```

## 固定上游版本

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`，不会静默追随上游 `main`。

## 测试与 CI

GitHub Actions 会真实执行：

1. 前端行为合约测试；
2. Shell 语法检查；
3. 下载并固定上游 Mini Metro 引擎；
4. Python 编译；
5. Algorithm Library / Planner / Protocol / Metrics / Battle / Arena / Experiments / Web 测试；
6. 真实引擎 smoke test；
7. 同算法同 Seed 严格平局与固定 dt 回归；
8. V1 vs V2 固定 Seeds、15 分钟候选 benchmark；
9. 启动 HTTP 单算法与双算法观战服务做真实请求验证。

## 清理

```bash
./scripts/clean.sh
```

彻底卸载直接删除仓库目录即可，不修改系统 Python。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本仓库新增代码同样采用 MIT License。
