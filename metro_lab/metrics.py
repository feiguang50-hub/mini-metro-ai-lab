from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pressure import PassengerPressure

_TOPOLOGY_ACTIONS = {"create_path", "replace_path", "remove_path", "buy_line"}


def _structured(observation: dict[str, Any]) -> dict[str, Any]:
    return observation["structured"]


def _state_metrics(observation: dict[str, Any]) -> tuple[int, int, float, int, int, int, int]:
    state = _structured(observation)
    stations = list(state.get("stations", ()))
    metros = list(state.get("metros", ()))
    fleet = state.get("fleet", {})

    waiting_counts = [int(item.get("passenger_count", 0)) for item in stations]
    network_waiting = sum(waiting_counts)
    peak_station_queue = max(waiting_counts, default=0)

    onboard = sum(len(item.get("passenger_ids", ())) for item in metros)
    capacity = sum(max(0, int(item.get("capacity", 0))) for item in metros)
    fleet_load = onboard / capacity if capacity > 0 else 0.0

    return (
        network_waiting,
        peak_station_queue,
        fleet_load,
        len(state.get("paths", ())),
        len(stations),
        int(fleet.get("locomotives_assigned", 0)),
        int(fleet.get("carriages_assigned", 0)),
    )


@dataclass
class EpisodeTelemetry:
    """Time-weighted network health metrics for one deterministic episode."""

    observed_ms: int = 0
    waiting_passenger_ms: float = 0.0
    fleet_load_ms: float = 0.0
    fleet_active_ms: int = 0
    at_risk_passenger_ms: float = 0.0
    overdue_passenger_ms: float = 0.0
    high_risk_ms: int = 0
    peak_network_waiting: int = 0
    peak_station_queue: int = 0
    peak_at_risk_passengers: int = 0
    peak_overdue_passengers: int = 0
    peak_wait_ms: int = 0
    peak_risk_pct: int = 0
    passenger_max_wait_time_ms: int = 0
    overdue_passenger_threshold: int = 0
    max_paths: int = 0
    max_stations: int = 0
    max_locomotives_assigned: int = 0
    max_carriages_assigned: int = 0
    non_noop_actions: int = 0
    topology_actions: int = 0

    def observe_initial(
        self,
        observation: dict[str, Any],
        pressure: PassengerPressure | None = None,
    ) -> None:
        self._observe_state(observation, elapsed_ms=0)
        if pressure is not None:
            self._observe_pressure(pressure, elapsed_ms=0)

    def record_action(self, action_type: str | None) -> None:
        if not action_type or action_type == "noop":
            return
        self.non_noop_actions += 1
        if action_type in _TOPOLOGY_ACTIONS:
            self.topology_actions += 1

    def record_transition(
        self,
        observation: dict[str, Any],
        *,
        elapsed_ms: int,
        pressure: PassengerPressure | None = None,
    ) -> None:
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative")
        elapsed_ms = int(elapsed_ms)
        self.observed_ms += elapsed_ms
        self._observe_state(observation, elapsed_ms=elapsed_ms)
        if pressure is not None:
            self._observe_pressure(pressure, elapsed_ms=elapsed_ms)

    def _observe_state(self, observation: dict[str, Any], *, elapsed_ms: int) -> None:
        (
            network_waiting,
            station_queue,
            fleet_load,
            paths,
            stations,
            locomotives,
            carriages,
        ) = _state_metrics(observation)

        self.peak_network_waiting = max(self.peak_network_waiting, network_waiting)
        self.peak_station_queue = max(self.peak_station_queue, station_queue)
        self.max_paths = max(self.max_paths, paths)
        self.max_stations = max(self.max_stations, stations)
        self.max_locomotives_assigned = max(self.max_locomotives_assigned, locomotives)
        self.max_carriages_assigned = max(self.max_carriages_assigned, carriages)

        if elapsed_ms:
            self.waiting_passenger_ms += network_waiting * elapsed_ms
            state = _structured(observation)
            metros = list(state.get("metros", ()))
            capacity = sum(max(0, int(item.get("capacity", 0))) for item in metros)
            if capacity > 0:
                self.fleet_load_ms += fleet_load * elapsed_ms
                self.fleet_active_ms += elapsed_ms

    def _observe_pressure(self, pressure: PassengerPressure, *, elapsed_ms: int) -> None:
        self.passenger_max_wait_time_ms = pressure.passenger_max_wait_time_ms
        self.overdue_passenger_threshold = pressure.overdue_passenger_threshold
        self.peak_at_risk_passengers = max(
            self.peak_at_risk_passengers, pressure.at_risk_passengers
        )
        self.peak_overdue_passengers = max(
            self.peak_overdue_passengers, pressure.overdue_passengers
        )
        self.peak_wait_ms = max(self.peak_wait_ms, pressure.max_wait_ms)
        self.peak_risk_pct = max(self.peak_risk_pct, pressure.risk_pct)

        if elapsed_ms:
            self.at_risk_passenger_ms += pressure.at_risk_passengers * elapsed_ms
            self.overdue_passenger_ms += pressure.overdue_passengers * elapsed_ms
            if pressure.risk_pct >= 75:
                self.high_risk_ms += elapsed_ms

    @property
    def average_waiting_passengers(self) -> float:
        if self.observed_ms <= 0:
            return 0.0
        return self.waiting_passenger_ms / self.observed_ms

    @property
    def waiting_passenger_seconds(self) -> float:
        return self.waiting_passenger_ms / 1000.0

    @property
    def average_fleet_load_pct(self) -> float:
        if self.fleet_active_ms <= 0:
            return 0.0
        return self.fleet_load_ms / self.fleet_active_ms * 100.0

    @property
    def at_risk_passenger_seconds(self) -> float:
        return self.at_risk_passenger_ms / 1000.0

    @property
    def overdue_passenger_seconds(self) -> float:
        return self.overdue_passenger_ms / 1000.0

    @property
    def high_risk_seconds(self) -> float:
        return self.high_risk_ms / 1000.0
