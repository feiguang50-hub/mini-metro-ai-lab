# 🚇 Mini Metro AI Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与策略进化** 的本地实验场。

它不重新发明游戏引擎，而是固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证版本作为底层模拟器，在上面提供：

- 🇨🇳 **全中文观战界面**：浏览器打开即可看线路、车站、列车和客流变化。
- 🚇 **平滑实时动画**：列车做视觉插值，站台直接显示乘客目标形状。
- 🧠 **算法实时决策**：展示当前判断、最近动作、执行结果和拥堵风险。
- 🗃️ **算法库**：观战页直接选择已经实现的算法；未完成算法也会显示开发状态。
- 👀 **沉浸观战模式**：一键隐藏 AI 面板，只看地铁网络运行。
- ⏯️ **暂停 / 1× / 2× / 4× / 重开**：适合看算法，也适合做可复现实验。
- 🏁 **固定 Seed 竞技场**：同一批随机种子、同一时间预算下公平比较算法。
- 📼 **实验档案与回放记录**：Arena 自动保存配置、结果、CSV、摘要和压缩回放流。
- 🔒 **完全本地运行**：默认只监听 `127.0.0.1`，不需要 OpenAI API，也不上传游戏状态。
- 🧹 **干净安装**：所有依赖留在项目目录的 `.venv` 和 `.vendor` 中，删除目录即可卸载。

> 当前版本：**0.4.0 / Experiment Artifacts + Replay Recording**。已经能留下可复现的实验黑匣子；浏览器回放播放器将在后续版本接入。

## 30 秒启动

需要 Linux、Git、[`uv`](https://docs.astral.sh/uv/) 和能访问 GitHub 的网络。

```bash
./run.sh
```

第一次运行会自动：

1. 下载固定版本的 `python_mini_metro` 到 `.vendor/`；
2. 使用 Python 3.13 创建 `.venv`；
3. 安装引擎依赖和本项目；
4. 启动本地观战页并自动打开浏览器。

默认地址：<http://127.0.0.1:8765>

## 🗃️ 算法库

观战页右侧有“算法库”。它直接读取后端算法注册表，而不是在网页里硬编码名称。

当前可运行：

- `greedy-v1` · **Greedy Planner V1** · baseline

已经规划但尚不可运行的算法也会出现在库中，并标记“开发中”：

- Balanced Greedy V2
- Beam Search
- Model Predictive Control (MPC)
- Monte Carlo Tree Search (MCTS)
- Policy + Value + Search
- Recurrent PPO

切换算法时会**保持当前 Seed 并自动重开本局**。这样你可以连续选择不同算法跑同一张局面，直接肉眼比较表现。

也可以从命令行指定启动算法：

```bash
./run.sh --algorithm greedy-v1
```

算法元数据统一放在：

```text
metro_lab/algorithms.py
```

新增算法只需要在这里注册一次，观战页和 Arena 会同时识别它。

## 观战模式

顶部地图区域提供两个轻量开关：

- **客流**：显示 / 隐藏站台乘客的目标形状。
- **沉浸观战**：隐藏 AI 侧栏，让地图占满可用宽度。

底部控制：

- **暂停 / 继续**
- **1× / 2× / 4×**
- **同 Seed 重开**
- **随机新局**

按 `Ctrl+C` 关闭服务。

## 当前算法：Greedy Planner V1

V1 是透明、稳定、可对照的基线：

1. 初始站点按几何距离构造短线路；
2. 新站以最小额外绕行代价插入现有线路；
3. 优先给没有机车的线路分配机车；
4. 高压力线路优先增加机车与车厢；
5. 通过拓扑冷却避免频繁重画线路。

它故意保持简单。后续算法必须先在 Arena 里证明自己更强，再获得 `candidate` / `champion` 等状态。

## 🏁 算法竞技场

第一次运行过 `./run.sh` 后：

```bash
.venv/bin/mini-metro-arena
```

默认使用 5 个固定 Seed，每局最多模拟 15 分钟。

自定义：

```bash
.venv/bin/mini-metro-arena --minutes 5
.venv/bin/mini-metro-arena --seeds 42 314 2026 4096 65537
.venv/bin/mini-metro-arena --algorithms greedy-v1
.venv/bin/mini-metro-arena --json
```

Arena 只允许选择**已经实现且可运行**的算法。它和观战页共用 `metro_lab/algorithms.py`，避免两个地方的算法名单漂移。

当前指标：

- 平均运送量
- 中位数
- 最低 / 最高运送量
- 游戏结束率
- 无效动作数量

算法进化、晋级、淘汰和复活记录见 [`docs/algorithm-history.md`](docs/algorithm-history.md)。

## 📼 实验档案与回放

从 0.4.0 开始，Arena 默认会把每次实验保存到：

```text
output/experiments/<timestamp>-<algorithm...>/
```

每个实验目录包含：

```text
config.json       # 算法、Seeds、时间预算、步长、引擎提交
results.json      # 机器可读的逐局结果与排行榜
episodes.csv      # 每个 algorithm × seed 一行
summary.md        # 人类可读摘要
replays/
  *.jsonl.gz      # 压缩回放流
```

回放采用带版本号的 gzip JSON Lines：

- 开局状态必记；
- 默认每 1000 ms 采样一次完整结构化状态；
- 每个非 `noop` 决策无论是否命中采样点都会记录；
- Game Over 会记录最终状态；
- Header 保存算法、Seed、步长、时间预算与底层引擎提交。

这样以后可以做真正的浏览器时间轴回放，而不用重新猜当时发生了什么。

常用选项：

```bash
# 只保存结果，不记回放
.venv/bin/mini-metro-arena --no-replays

# 完全不落盘，只看终端输出
.venv/bin/mini-metro-arena --no-save

# 更密集的回放采样
.venv/bin/mini-metro-arena --replay-sample-ms 500

# 自定义实验根目录
.venv/bin/mini-metro-arena --output-dir /tmp/metro-experiments
```

`output/` 已被 Git 忽略。我们只会把有研究价值的代表性实验晋升进仓库历史，不让普通跑分把仓库撑成数据仓库。

## 设计原则

Mini Metro 的核心魅力来自：**城市长大 → 网络变差 → 重画线路 → 恢复秩序**。

我们的界面原则：

- 地图永远是主角；
- AI 信息是可隐藏的辅助层；
- 客流尽量用图形表达；
- 动画只改善观看，不改变底层模拟；
- 不复制 Mini Metro 的商业素材或资源文件。

实验原则：

- 同轮比较使用相同 Seeds、步长和时间预算；
- 小样本只能作为候选证据；
- 新冠军必须明确击败当前冠军；
- 失败算法保留历史，不删除研究记忆；
- 实验结果必须能追溯到算法版本和引擎版本。

## 架构

```text
浏览器观战页
    │
    ├── Algorithm Library
    │       │
    │       ▼
    │   algorithms.py
    │       │
    │       ├──────────────┐
    │       ▼              ▼
    │   LabRuntime      Headless Arena
    │       │              │
    └───────┴──────┬───────┘
                   ▼
              MiniMetroEnv
                   │
                   ▼
          python_mini_metro

Headless Arena
    │
    ├── results / summaries
    └── ReplayWriter
            │
            ▼
      output/experiments
```

## 项目结构

```text
metro_lab/
  algorithms.py   # 算法注册表与元数据
  engine.py       # 引擎适配与实时模拟线程
  planner.py      # Greedy Planner V1
  arena.py        # 固定 Seed 无头竞技场
  experiments.py  # 实验目录、CSV/JSON/Markdown、回放记录器
  server.py       # 本地 HTTP API + 静态页面
web/
  index.html
  styles.css
  algorithm-library.css
  app.js
docs/
  algorithm-history.md
scripts/
  bootstrap.sh
run.sh
tests/
  test_algorithm_library.py
  test_planner.py
  test_engine_smoke.py
  test_arena.py
  test_experiments.py
  test_web_contract.py
```

## 固定的上游版本

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`。

## 测试与 CI

GitHub Actions 会真实执行：

1. Shell 语法检查；
2. 下载并固定上游 Mini Metro 引擎；
3. Python 编译；
4. Algorithm Library / Planner / Arena / Experiments / Web 合约单测；
5. 真实引擎 smoke test；
6. 真实引擎短局回放写入测试；
7. 启动本地 HTTP 服务并请求 `/api/state`。

## 清理

```bash
./scripts/clean.sh
```

彻底卸载则直接删除仓库目录即可，不修改系统 Python。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License。详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

本仓库新增代码同样采用 MIT License。
