# 🚇 Mini Metro AI Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与可复现实验** 的本地实验场。

固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证提交作为底层模拟器，在其上提供中文观战、算法库、固定 Seed Arena、同步 Battle、版本化场景、压力指标、实验档案和回放。

> 当前版本：**0.10.0 / heuristic generation frozen · search planning next**

## 30 秒启动

需要 Linux、Git、[`uv`](https://docs.astral.sh/uv/) 和能访问 GitHub 的网络。

```bash
./run.sh
```

首次启动会在项目目录内创建 `.venv`、下载固定版本引擎到 `.vendor`，然后打开本地观战页：

```text
http://127.0.0.1:8765
```

不修改系统 Python，不需要 OpenAI API，也不上传游戏状态。

## 🧠 算法库

当前真正可运行的算法有四个：

| ID | 算法 | 状态 | 说明 |
| --- | --- | --- | --- |
| `greedy-v1` | Greedy Planner V1 | `baseline` | 几何距离 + 即时压力，当前默认基线 |
| `greedy-v1-1-pressure` | Greedy V1.1 Pressure Rescue | `archived` | V1 拓扑 + 单次候车压力救火；资格赛与 V1 基本打平，保留为可运行研究样本 |
| `balanced-greedy-v2` | Balanced Greedy V2 | `candidate` | 站型多样性、线路长度与压力的多目标启发式 |
| `balanced-greedy-v2-1` | Balanced Greedy V2.1 Rescue | `candidate` | 修复 V2 单线扩容死区，并从公开 observation 重建候车年龄进行定点救火 |

规划中但尚不可运行：Beam Search、MPC、MCTS、Policy + Value + Search、Recurrent PPO。

浏览器算法库直接读取 `metro_lab/algorithms.py`。切换算法会保持当前 Seed 并重开同一局，便于肉眼公平比较。归档算法仍然可以手动选择，不会因为“输了”而从历史里消失。

```bash
./run.sh --algorithm greedy-v1-1-pressure
```

### 为什么默认仍是 Greedy V1

V2.1 的冻结 Stress qualification 没有稳定击败 V1：20 个 holdout Seeds 上 V1 平均 **107.30**、V2.1 **103.75**，paired 为 **8 胜 / 11 负 / 1 平**。

V1.1 后续修复了“25 秒后连续倾倒整支车队”的过度救火问题，在新的 5-Seed 开发集上 Stress 从 V1 的 83.0 提升到 **85.8**。参数随即冻结，并启用另一套从未参与调参的 20-Seed qualification：

| V1.1 frozen holdout | Greedy V1 | Greedy V1.1 |
| --- | ---: | ---: |
| Classic 平均运送 | **39.75** | 39.70 |
| Stress 平均运送 | 96.55 | **96.60** |
| Stress 平均候车 | 2.00 | **1.93** |
| Stress Peak Risk | 99.4% | **97.8%** |
| Stress 高危持续 | 37.8s | **34.1s** |
| Stress Game Over | 85% | 85% |
| Stress invalid rate | **37.0%** | 39.5% |

Stress paired 为 **2 胜 / 3 负 / 15 平**，中位差 0，均值只 +0.05；同时出现 `+46/+23` 和 `-42/-15/-11` 的双向大波动。结论是：Pressure Rescue 能救出部分危局，但不是稳定升级，因此 **V1.1 归档、Greedy V1 继续默认，heuristic 微调到此冻结**。

完整实验演化、失败模式和资格赛纪律见 [`docs/algorithm-history.md`](docs/algorithm-history.md)。

## 👀 中文实时观战

单算法页面提供：

- 地铁图实时绘制
- 列车平滑移动
- 站台乘客目标形状
- Passenger Pressure 风险
- 当前 AI 决策与最近动作
- 1× / 2× / 4×
- 同 Seed 重开 / 随机新局
- 客流开关 / 沉浸观战

Passenger Pressure 不再拿“单站人数”硬除一个无关阈值，而是与固定上游引擎的真实失败条件对齐：观察等待最久的一组乘客距离最大等待时间还有多远。

## ⚔️ 浏览器双算法 Battle

启动后进入 `/battle.html`，可以让两个算法在：

- 相同 Seed
- 相同 `dt_ms`
- 相同预算
- 相同 Stress 站点时间表
- 相同 Simulation Protocol

下同步推进。

服务端发布原子 paired snapshot，刷新网页不会多走模拟步数。一侧 Game Over 后冻结，另一侧继续到共同预算。

CLI 也可直接对战：

```bash
.venv/bin/mini-metro-battle \
  greedy-v1 greedy-v1-1-pressure \
  --scenario stress-v1 \
  --seed 42 \
  --minutes 15
```

## 🏁 Arena V2

```bash
.venv/bin/mini-metro-arena
```

例：

```bash
.venv/bin/mini-metro-arena \
  --scenario stress-v1 \
  --algorithms greedy-v1 balanced-greedy-v2 balanced-greedy-v2-1 \
  --seeds 42 314 2026 4096 65537 \
  --minutes 15
```

Arena 不只记录最终 deliveries，还记录：

- `deliveries/min`
- 实际生存时间
- 时间加权平均候车人数
- passenger waiting seconds
- Peak Passenger Pressure
- 最长等待时间
- 高危持续时间
- 全网与单站候车峰值
- 时间加权车队载客率
- 最大线路 / 站点 / 机车 / 车厢规模
- 非 `noop` 动作、拓扑动作、无效动作与 invalid rate
- Game Over 率

排行榜仍以 deliveries 为主排序，健康指标负责解释胜负，不偷偷发明一个难审计的“综合神分”。

## 🌆 版本化 Scenario

目前正式场景：

| ID | 用途 | 规则 |
| --- | --- | --- |
| `classic-v1` | 历史兼容 / 低压基线 | 保持固定上游原始站点推进逻辑 |
| `stress-v1` | 高压资格赛 / 浏览器观战 | 开局初始站，此后每 45 秒模拟时间开放一个新站直到上限 |

不同 scenario 的成绩不会被混进同一个排行榜。升级场景必须新建版本，不能静默改旧赛道。

## ⏱️ Simulation Protocol V2

固定上游引擎有一个重要语义：**被拒绝的动作本身不走时**。

Protocol V2 因此规定：

1. planner 每轮提交一个动作；
2. 有效动作正常推进固定 `dt`；
3. 无效动作仍记为 invalid，但随后用 `noop` 消耗同一轮 `dt`；
4. 除非 Game Over，固定 15 分钟预算就必须真的经历完整 15 分钟城市时间。

Arena、CLI Battle、浏览器 Battle 和单算法 Viewer 共用这套时间语义。

## 🧪 冻结资格赛

算法实验明确区分：

- **development seeds**：允许诊断和修改算法；
- **holdout qualification seeds**：参数冻结后才运行，看到结果后禁止反向调同一版本。

V2.1 与 V1.1 都拥有各自独立、预先冻结的 20-Seed qualification。已结束算法的资格赛保留为 `workflow_dispatch` 手动可复现工作流，不在普通 PR 上反复烧完整研究预算。

新冠军必须同时满足：开发集有改进、冻结资格赛能复现、Classic 不出现不可接受回退、健康指标没有隐藏灾难。

## 📼 实验档案与回放

Arena 默认保存到：

```text
output/experiments/<timestamp>-<scenario>-<algorithm...>/
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

记录中显式包含引擎提交、场景、Simulation Protocol、算法、Seeds、步长和预算。

```bash
.venv/bin/mini-metro-arena --no-replays
.venv/bin/mini-metro-arena --no-save
.venv/bin/mini-metro-arena --json
```

`output/` 被 Git 忽略，普通跑分不会污染仓库。

## 架构

```text
                    Algorithm Library
                           │
                    algorithms.py
                     │           │
                     ▼           ▼
                 LabRuntime    Arena V2
                     │           │
                     │      Metrics / Replay
                     │           │
                     ├───────────┴───────────┐
                     ▼                       ▼
                MiniMetroEnv          Simulation Protocol V2
                                             │
                               ┌─────────────┴─────────────┐
                               ▼                           ▼
                           CLI Battle                  Live Battle
                               │                           │
                               ▼                           ▼
                          MiniMetroEnv                MiniMetroEnv × 2
```

## 项目结构

```text
metro_lab/
  algorithms.py          # 算法注册表
  planner.py             # Greedy V1
  balanced_planner.py    # Balanced V2
  rescue_planner.py      # V1.1 / V2.1 Pressure Rescue
  scenarios.py           # Classic / Stress 场景注册表
  simulation.py          # Protocol V2
  pressure.py            # Passenger Pressure
  metrics.py             # Arena V2 健康指标
  arena.py               # 固定 Seed 竞技场
  battle.py              # CLI 同 Seed Battle
  live_battle.py         # 浏览器 paired runtime
  engine.py              # 单算法实时 runtime
  experiments.py         # 结果 / ReplayWriter
  server.py              # 本地 HTTP API
web/
  index.html
  battle.html
  app.js
  battle.js
  map-renderer.js
docs/
  algorithm-history.md
tests/
  ...
```

## 测试与 CI

普通 GitHub Actions 会真实执行：

1. 前端行为测试；
2. Shell 语法检查；
3. 下载并 checkout 固定上游引擎；
4. Python 编译与完整单测 / 真实引擎 smoke；
5. 同算法同 Seed 严格平局与 fixed-dt 回归；
6. Classic / Stress 小型开发 benchmark；
7. HTTP 单算法和双算法真实请求 smoke。

冻结资格赛独立保存为手动研究门禁，避免文档或前端改动重复跑几十个长局。

## 固定上游版本

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`，不会静默追随上游 `main`。

## 清理

```bash
./scripts/clean.sh
```

彻底卸载直接删除仓库目录即可。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本仓库新增代码同样采用 MIT License。
