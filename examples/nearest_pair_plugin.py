from __future__ import annotations

from itertools import combinations
from math import hypot

from metro_lab.action import (
    AssignLocomotiveAction,
    CreateLineAction,
    NoOpAction,
    PlanningDecision,
)
from metro_lab.plugin import AlgorithmMetadata
from metro_lab.problem import MetroPlanningState, StationState


class NearestPairExample:
    """Minimal external plugin example, intentionally not a competitive policy."""

    metadata = AlgorithmMetadata(
        id="example-nearest-pair",
        name="Example: Nearest Pair",
        version="0.1",
        family="example",
        description="Minimal drop-in plugin that opens the nearest station pair.",
    )

    def reset(self, state: MetroPlanningState) -> None:
        del state

    @staticmethod
    def _distance(a: StationState, b: StationState) -> float:
        return hypot(a.x - b.x, a.y - b.y)

    def act(self, state: MetroPlanningState) -> PlanningDecision:
        if not state.lines and len(state.stations) >= 2:
            a, b = min(
                combinations(state.stations, 2),
                key=lambda pair: self._distance(pair[0], pair[1]),
            )
            return PlanningDecision(
                CreateLineAction((a.id, b.id)),
                "建立最近站点对",
                "示例插件只演示标准 Problem/Action Contract 接入。",
            )

        if state.lines and state.fleet.locomotives_available > 0:
            served_line_ids = {
                vehicle.path_id
                for vehicle in state.vehicles
                if vehicle.path_id is not None
            }
            empty = next(
                (line for line in state.lines if line.id not in served_line_ids),
                None,
            )
            if empty is not None:
                return PlanningDecision(
                    AssignLocomotiveAction(empty.id),
                    "投放示例机车",
                    "让刚建立的线路开始运行。",
                )

        return PlanningDecision(
            NoOpAction(),
            "示例等待",
            "该示例到此为止，请复制文件并替换为你的算法。",
        )


PLUGIN_FACTORY = NearestPairExample
