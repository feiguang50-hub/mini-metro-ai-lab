# 🔭 Search Planning Protocol

Mini Metro AI Lab 从 0.10 之后停止继续堆 heuristic 小阈值，下一代进入显式前瞻规划。这个文件先定义**什么样的搜索结果才算合法**，再讨论 Beam / MPC / MCTS 谁更强。

## 为什么先做协议

固定上游引擎可以完整序列化当前游戏，而且序列化文档包含 RNG 状态。这同时带来能力和陷阱：

- 能力：当前局面可以精确保存 / 恢复，因此 rollout 不需要重写一套粗糙模拟器；
- 陷阱：如果候选动作直接从真实快照恢复并向前跑，它会复现**真实 episode 即将发生的隐藏随机未来**。

上游 `scripts/search_policy.py` 已经实测踩过这个坑：单一序列化 future 中候选差异只有几十 deliveries，而同一个候选在不同 futures 之间的波动也能达到同一量级。把单一真实 future 当“确定未来”会产生 clairvoyant / oracle search，成绩无法由只看 observation 的真实 Agent 复现。

因此本项目把“避免未来泄漏”放在搜索深度之前。

## Protocol S1

### 1. Snapshot fidelity

搜索宿主可以在 quiescent boundary 捕获完整游戏快照。精确 restore 只用于测试：必须证明 restore 后当前可见状态与 live board 一致。

### 2. No oracle future

算法打分入口**不提供 exact restore**。每次 rollout 必须先替换快照中的 gameplay RNG，再恢复模拟环境。

如果某个实验显式使用原始 RNG，它只能标记为 `oracle diagnostic`，不得进入算法排行榜或 qualification。

### 3. Common random numbers

在同一个真实决策点：

1. 先生成固定的 future keys；
2. 候选 A、B、C 都使用**完全相同的一组 keys**；
3. 每个候选的价值是这些 sampled futures 上的聚合结果。

这样未来噪声被 paired，比“每个候选各抽各的随机未来”更容易隔离动作本身的差异。

### 4. Receding horizon

即使搜索得到一个多步动作序列，也只把**第一步**提交给真实环境。下一次决策重新观察、重新采样 futures、重新规划。

这避免把旧预测当成事实，也让规划能吸收真实新站、乘客和资源变化。

### 5. Search budget is explicit

每个算法必须记录：

- candidate shortlist 大小；
- sampled future 数量；
- horizon / rollout stop rule；
- 每次决策最大 simulation steps；
- planner wall-clock time；
- value function 组成；
- search 触发次数和 override 次数。

不能用“搜索更久当然更强”掩盖不可用的实时成本。

## 已确认的上游经验

Pinned upstream 的搜索实验已经提供三个重要约束：

1. **固定短 horizon 会偏向 WAIT。** 关键结构动作之间可能相隔数百到数千 decision ticks，短 rollout 只看到动作即时成本，看不到延迟收益。
2. **序列化可复现不等于世界确定。** Save document 保存 RNG，因此 exact rollout 是重播一个隐藏未来，不是对未来分布做估计。
3. **多 sampled futures + common random numbers 才能公平比较候选。** 上游修正版对每个候选使用相同 future keys 做平均。

这些结论优先于“先把 Beam 写出来再说”。

## 与 stochastic MPC 的关系

这里借用的是 stochastic / scenario MPC 的基本结构，而不是照搬连续控制数学：

- 当前状态作为规划起点；
- 对不确定未来抽取有限 scenarios；
- 在有限规划问题中比较动作；
- 只执行当前最优序列的第一步；
- 下一次状态到来后重新求解。

Mini Metro 的动作空间是离散结构动作，因此候选生成与搜索本身更接近 Beam / discrete MPC，但“不确定未来需要 scenario sampling”和“receding horizon”原则保持一致。

## 第一阶段实现边界

`metro_lab/rollout.py` 只负责：

- 捕获 pinned engine save snapshot；
- 确认精确 restore 的当前状态保真；
- 生成确定性的 sampled future keys；
- 对 save document 深拷贝并替换 Python / NumPy RNG；
- 创建隔离 rollout env；
- 重置 reward baseline，避免把历史 deliveries 当 rollout reward。

它**不负责**：

- 选候选动作；
- 定义 value function；
- 决定 Beam width；
- 偷读真实未来；
- 直接成为 Algorithm Library 的可选算法。

只有这一层通过真实引擎 CI 后，才进入 Search Planner V1。

## 下一步

1. 建立候选动作生成器：baseline action + WAIT + 少量合法结构替代；
2. 建立多 future paired evaluator；
3. 先做 one-decision stochastic lookahead probe，证明它不是 oracle；
4. 再比较 Beam Search 与 receding-horizon MPC 形式；
5. 参数冻结后使用全新 qualification，而不是复用 V1.1 的 holdout。
