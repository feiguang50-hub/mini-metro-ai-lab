# 🚇 Mini Metro Lab / 地铁算法实验室

一个面向 **Mini Metro 算法研究、实时观战与策略进化** 的本地实验场。

它不重新发明游戏引擎，而是固定使用 [`yanfengliu/python_mini_metro`](https://github.com/yanfengliu/python_mini_metro) 的已验证版本作为底层模拟器，在上面提供：

- 🇨🇳 **全中文观战界面**：浏览器打开即可看线路、车站、列车和拥堵变化。
- 🧠 **算法实时决策**：右侧展示当前判断、最近动作和风险指标。
- ⏯️ **暂停 / 1× / 2× / 4× / 重开**：适合看算法，也适合做实验。
- 🧪 **算法可插拔**：当前自带 `Greedy Planner V1`，后续可替换为 MPC、Beam Search、MCTS、Policy/Value 等。
- 🔒 **完全本地运行**：默认只监听 `127.0.0.1`，不需要 OpenAI API，也不上传游戏状态。
- 🧹 **干净安装**：所有依赖留在项目目录的 `.venv` 和 `.vendor` 中，删除目录即可卸载。

> 当前定位：**V1 可观战基线**。先把环境、观看体验和算法接口做稳，再进行算法竞赛与强化学习。

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

## 控制

- **暂停 / 继续**：停止或恢复模拟。
- **1× / 2× / 4×**：改变模拟推进速度。
- **同种子重开**：复现同一局，适合比较算法。
- **随机新局**：换一个 seed。

按 `Ctrl+C` 关闭服务。

## 当前算法：Greedy Planner V1

V1 的目标不是冒充“最优算法”，而是提供一个透明、稳定、可对照的基线：

1. 初始站点按几何距离构造短线路；
2. 新站出现后，以最小额外绕行代价插入现有线路；
3. 优先给没有机车的线路分配机车；
4. 当站点压力升高时，把可用机车和车厢投向最繁忙线路；
5. 每次拓扑修改都有冷却时间，避免算法频繁重画线路。

下一阶段会让以下算法在相同 seeds 上公平对战：

- Heuristic / Greedy
- Beam Search
- Model Predictive Control (MPC)
- Monte Carlo Tree Search (MCTS)
- Search + Value Network
- Policy + Value + Search
- PPO / Recurrent PPO（作为学习型对照组）

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
```

我们刻意把 **引擎、算法、前台** 分开。这样优化算法时不用重写 UI，上游引擎升级时也能明确验证行为差异。

## 项目结构

```text
metro_lab/
  engine.py       # 引擎适配与实时模拟线程
  planner.py      # Greedy Planner V1
  server.py       # 本地 HTTP API + 静态页面
web/
  index.html
  styles.css
  app.js          # Canvas 实时渲染
scripts/
  bootstrap.sh    # 固定引擎 + Python 环境
run.sh            # 一键启动
```

## 固定的上游版本

为保证实验可复现，V1 固定：

```text
python_mini_metro commit: 382d7cc65da566ac01d8151921c203c25418eacd
```

升级引擎必须显式修改 `metro_lab/config.py`，而不是静默跟随上游 `main`。

## 清理

只清运行环境、保留源码：

```bash
./scripts/clean.sh
```

彻底卸载则直接删除仓库目录即可，不修改系统 Python。

## 来源与许可

底层引擎 `python_mini_metro` 由 Yanfeng Liu 开发并采用 MIT License。详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

本仓库新增代码同样采用 MIT License。
