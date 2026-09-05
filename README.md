# 🚇 Mini Metro AI Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与策略进化** 的本地实验场。

它不重新发明游戏引擎，而是固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证版本作为底层模拟器，在上面提供：

- 🇨🇳 **全中文观战界面**：浏览器打开即可看线路、车站、列车和客流变化。
- 🚇 **平滑实时动画**：列车做视觉插值，站台直接显示乘客目标形状，而不是只显示计数。
- 🧠 **算法实时决策**：展示当前判断、最近动作、执行结果和拥堵风险。
- 👀 **沉浸观战模式**：一键隐藏 AI 面板，只看地铁网络运行。
- ⏯️ **暂停 / 1× / 2× / 4× / 重开**：适合看算法，也适合做可复现实验。
- 🧪 **算法可插拔**：当前自带 `Greedy Planner V1`，后续可加入 MPC、Beam Search、MCTS、Policy/Value 等。
- 🏁 **固定 Seed 竞技场**：同一批随机种子、同一时间预算下公平比较算法，不凭感觉判断“变强了”。
- 🔒 **完全本地运行**：默认只监听 `127.0.0.1`，不需要 OpenAI API，也不上传游戏状态。
- 🧹 **干净安装**：所有依赖留在项目目录的 `.venv` 和 `.vendor` 中，删除目录即可卸载。

> 当前版本：**0.2.0 / Viewer V2 + Arena 基础设施**。先把观看、测量和实验方法做稳，再开始系统性优化算法。

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

之后再次运行只需：

```bash
./run.sh
```

默认地址：<http://127.0.0.1:8765>

## 观战模式

顶部地图区域提供两个轻量开关：

- **客流**：显示 / 隐藏站台乘客的目标形状。
- **沉浸观战**：隐藏 AI 侧栏，让地图占满可用宽度；再次点击“显示 AI”即可恢复。

底部控制：

- **暂停 / 继续**：停止或恢复模拟。
- **1× / 2× / 4×**：改变模拟推进速度。
- **同 Seed 重开**：复现同一局，适合比较算法。
- **随机新局**：换一个 seed。

按 `Ctrl+C` 关闭服务。

## 当前算法：Greedy Planner V1

V1 的目标不是冒充“最优算法”，而是提供一个透明、稳定、可对照的基线：

1. 初始站点按几何距离构造短线路；
2. 新站出现后，以最小额外绕行代价插入现有线路；
3. 优先给没有机车的线路分配机车；
4. 当站点压力升高时，把可用机车和车厢投向最繁忙线路；
5. 每次拓扑修改都有冷却时间，避免算法频繁重画线路。

它故意保持简单。后续算法必须先在 Arena 里证明自己更强，再进入默认观战模式。

## 🏁 算法竞技场

第一次运行过 `./run.sh` 后，项目会安装一个本地命令：

```bash
.venv/bin/mini-metro-arena
```

默认使用 5 个固定 seed，每局最多模拟 15 分钟：

```bash
.venv/bin/mini-metro-arena
```

缩短测试时间：

```bash
.venv/bin/mini-metro-arena --minutes 5
```

自定义随机种子：

```bash
.venv/bin/mini-metro-arena --seeds 42 314 2026 4096 65537
```

机器可读结果：

```bash
.venv/bin/mini-metro-arena --json
```

当前排行榜只会看到 `greedy-v1`，因为它是基线。新增算法后会在**完全相同的 seeds、步长和时间预算**下比较：

- 平均运送量
- 中位数
- 最低 / 最高运送量
- 游戏结束率
- 无效动作数量

下一阶段候选：

- Balanced Heuristic / Greedy V2
- Beam Search
- Model Predictive Control (MPC)
- Monte Carlo Tree Search (MCTS)
- Search + Value Network
- Policy + Value + Search
- PPO / Recurrent PPO（学习型对照组）

## 设计原则

Mini Metro 本身的核心魅力来自一个很清楚的循环：**城市长大 → 网络变差 → 玩家重画线路 → 网络重新获得秩序**。这个实验室不会把画面堆成服务器监控台，也不会为了“AI 感”塞满无意义指标。

我们的界面原则：

- 地图永远是主角；
- AI 信息是可隐藏的辅助层；
- 客流尽量用图形表达，不用密密麻麻的数字；
- 所有动画只改善观看，不改变底层模拟；
- 不复制 Mini Metro 的商业素材或资源文件，只借鉴“极简交通图”的设计语言。

## 架构

```text
浏览器观战页
    │  /api/state  /api/control
    ▼
本地 Lab Server
    │
    ├── Algorithm  ← 可替换策略
    │
    ▼
MiniMetroEnv
    │
    ▼
python_mini_metro（固定版本引擎）

同一 Algorithm
    │
    ▼
Headless Arena
    │
    ├── 固定 Seeds
    ├── 固定时间预算
    └── 可复现排行榜
```

我们刻意把 **引擎、算法、前台、评测** 分开。这样优化算法时不用重写 UI，上游引擎升级时也能明确验证行为差异。

## 项目结构

```text
metro_lab/
  engine.py       # 引擎适配与实时模拟线程
  planner.py      # Greedy Planner V1
  arena.py        # 固定 Seed 无头竞技场
  server.py       # 本地 HTTP API + 静态页面
web/
  index.html
  styles.css
  app.js          # Canvas 实时渲染 + 平滑动画
scripts/
  bootstrap.sh    # 固定引擎 + Python 环境
run.sh            # 一键启动
tests/
  test_planner.py
  test_engine_smoke.py
  test_arena.py
  test_web_contract.py
```

## 固定的上游版本

为保证实验可复现，当前固定：

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`，而不是静默跟随上游 `main`。

## 测试与 CI

GitHub Actions 会真实执行：

1. Shell 脚本语法检查；
2. 下载并固定上游 Mini Metro 引擎；
3. Python 编译；
4. Planner / Arena / Web 合约单测；
5. 真实引擎 smoke test；
6. 启动本地 HTTP 服务并请求 `/api/state`。

目标不是“CI 有个绿勾”，而是保证 clone 到一台干净 Linux 机器后，项目确实能启动。

## 清理

只清运行环境、保留源码：

```bash
./scripts/clean.sh
```

彻底卸载则直接删除仓库目录即可，不修改系统 Python。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License。详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

本仓库新增代码同样采用 MIT License。
