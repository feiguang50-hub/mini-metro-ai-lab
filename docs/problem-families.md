# Problem Families / 问题族

## 目标

Mini Metro AI Lab 的长期目标不是复制一个游戏规则集合，而是研究 **metro line planning** 的数学问题。

因此需要区分三件事：

1. **Problem Family**：哪些数学结构正在被研究；
2. **Scenario**：在某个 Problem Family 下的一套可复现实例生成/演化规则；
3. **Backend**：真正执行状态转移、客流和约束的模拟实现。

一个 Scenario 可以更换 backend 实现，只要它仍满足同一问题契约；一个 backend 也可以承载多个 Problem Families。

## Minimum Sufficient Realism

平台采用“最小充分现实性”原则：

- 保留可能改变最优解结构、算法排序或鲁棒性的现实因素；
- 删除只增加模拟复杂度、却不帮助研究线路规划核心问题的细节；
- 每加入一个维度，都必须说明它代表什么数学结构、考察算法什么能力，以及如何公平评测。

复杂性不是目标，**可解释地逼近真实规划问题**才是目标。

## Contract V1 dimensions

Problem Family Contract V1 固定六个正交研究维度：

| Dimension | 数学含义 | 当前状态 |
| --- | --- | --- |
| `geometry` | 站点空间位置、线路连接与路径结构 | 已覆盖 |
| `demand` | 客流需求如何影响网络设计 | 已覆盖，但目前仍来自 pinned simulator，而非显式 OD benchmark |
| `capacity` | 有限车辆与承载能力如何约束方案 | 已覆盖 |
| `infrastructure` | 建设成本、河流/障碍、可建设边等可行域约束 | 尚未实现 |
| `uncertainty` | 未知未来需求/事件下的鲁棒规划 | 尚未实现 |
| `evolution` | 规划域随时间发生变化 | 部分覆盖，目前仅有外生站点开放 |

这些维度可以组合，而不是形成互不兼容的“难度模式”。

## Current families

### `simulator-baseline-v1`

Dimensions:

- `geometry`
- `demand`
- `capacity`

由 `classic-v1` 承载，作为历史可比基线。

明确不声称：

- 显式 OD matrix；
- 建设成本 / 地理障碍；
- 随机未来信息边界；
- 土地利用与线路建设的反馈。

### `exogenous-growth-v1`

Dimensions:

- `geometry`
- `demand`
- `capacity`
- `evolution`

由 `stress-v1` 承载。相较 baseline，候选站点集合按模拟时钟逐步开放，因此测试算法面对**变化中的规划域**时的适应能力。

这里的 `evolution` 只表示外生站点开放，不表示人口、土地利用或 OD demand 会因为新线路反向变化。

## 为什么先做 taxonomy，而不是马上加复杂机制

Transit Network Design Problem 的既有研究通常把 route network design、frequency setting、用户成本、运营者成本、需求与约束分开建模，并在此基础上研究多目标权衡。近年的不确定性研究同样强调：如果没有清晰的实例定义和共同术语，不同算法的结果很难真正比较。

因此本项目后续不会用“更真实”作为加机制的充分理由。一个新维度进入正式 benchmark 前至少需要：

1. 数学变量和约束定义；
2. 可复现的实例生成规则或公开数据映射；
3. 算法可见信息边界；
4. 独立评价指标；
5. 与已有问题族的对照实验。

## Planned progression

下一批真正值得实现的问题结构优先级为：

1. **Explicit Demand V1**：从隐式 passenger generation 迈向显式 OD / time-dependent demand；
2. **Infrastructure V1**：建设成本与少量有数学意义的空间障碍；
3. **Uncertainty V1**：训练/规划可见信息与 holdout future 明确分离；
4. **Integrated Capacity / Frequency**：把线路结构和服务频率/运力配置纳入同一公平预算；
5. **Endogenous Evolution**：只有在前面结构稳定后，才研究线路建设对未来需求的反馈。

每一层都必须能够单独关闭，确保我们知道一个算法究竟是因为哪种结构变强或变弱。
