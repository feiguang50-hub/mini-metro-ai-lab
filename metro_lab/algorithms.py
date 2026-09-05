from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from .balanced_planner import BalancedGreedyPlanner
from .planner import GreedyPlanner

PlannerFactory = Callable[[], Any]


@dataclass(frozen=True)
class AlgorithmSpec:
    id: str
    name: str
    family: str
    version: str
    status: str
    summary: str
    tags: tuple[str, ...]
    factory: PlannerFactory | None = None
    default: bool = False

    @property
    def available(self) -> bool:
        return self.factory is not None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("factory", None)
        data["tags"] = list(self.tags)
        data["available"] = self.available
        return data


ALGORITHM_SPECS: tuple[AlgorithmSpec, ...] = (
    AlgorithmSpec(
        id="greedy-v1",
        name="Greedy Planner V1",
        family="启发式",
        version="1.0",
        status="baseline",
        summary="几何距离 + 即时拥堵的透明基线。新站按最小绕行插入，高压力线路优先扩容。",
        tags=("低计算量", "可解释", "基线"),
        factory=GreedyPlanner,
        default=True,
    ),
    AlgorithmSpec(
        id="balanced-greedy-v2",
        name="Balanced Greedy V2",
        family="启发式",
        version="2.0-candidate",
        status="candidate",
        summary="同时考虑站型多样性、线路长度、客流压力和网络分流机会的多目标启发式。",
        tags=("候选", "多目标", "可解释"),
        factory=BalancedGreedyPlanner,
    ),
    AlgorithmSpec(
        id="beam-search",
        name="Beam Search",
        family="搜索",
        version="0.x",
        status="planned",
        summary="保留一批最有希望的候选线路方案，向前搜索多步后再落子。",
        tags=("开发中", "前瞻搜索"),
    ),
    AlgorithmSpec(
        id="mpc",
        name="Model Predictive Control",
        family="模型式规划",
        version="0.x",
        status="planned",
        summary="利用可复制模拟器滚动预测未来，在有限规划窗口中选择当前动作。",
        tags=("开发中", "滚动规划"),
    ),
    AlgorithmSpec(
        id="mcts",
        name="Monte Carlo Tree Search",
        family="搜索",
        version="0.x",
        status="planned",
        summary="对未来动作分支做蒙特卡洛采样，用搜索预算换取更强的长期决策。",
        tags=("开发中", "长期决策"),
    ),
    AlgorithmSpec(
        id="policy-value-search",
        name="Policy + Value + Search",
        family="学习 + 搜索",
        version="0.x",
        status="planned",
        summary="策略网络给候选排序，价值网络估值，搜索负责最终决策。",
        tags=("开发中", "长期目标"),
    ),
    AlgorithmSpec(
        id="recurrent-ppo",
        name="Recurrent PPO",
        family="强化学习",
        version="0.x",
        status="planned",
        summary="作为纯学习型对照组，检验端到端策略在同一环境中的上限与稳定性。",
        tags=("开发中", "对照组"),
    ),
)

ALGORITHMS: dict[str, AlgorithmSpec] = {spec.id: spec for spec in ALGORITHM_SPECS}
DEFAULT_ALGORITHM_ID = next(spec.id for spec in ALGORITHM_SPECS if spec.default)


def get_algorithm_spec(algorithm_id: str) -> AlgorithmSpec:
    try:
        return ALGORITHMS[algorithm_id]
    except KeyError as exc:
        raise ValueError(f"unknown algorithm: {algorithm_id}") from exc


def create_planner(algorithm_id: str):
    spec = get_algorithm_spec(algorithm_id)
    if not spec.available or spec.factory is None:
        raise ValueError(f"algorithm is not available yet: {algorithm_id}")
    return spec.factory()


def algorithm_catalog() -> list[dict[str, Any]]:
    return [spec.public() for spec in ALGORITHM_SPECS]


def available_algorithm_ids() -> list[str]:
    return [spec.id for spec in ALGORITHM_SPECS if spec.available]
