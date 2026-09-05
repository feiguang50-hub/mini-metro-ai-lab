from __future__ import annotations

import copy

import pytest

from metro_lab.problem import PROBLEM_CONTRACT_VERSION, PROBLEM_ID, state_from_observation


def _observation() -> dict:
    return {
        "structured": {
            "time_ms": 12_500,
            "is_game_over": False,
            "deliveries": 7,
            "line_credits": 2,
            "unlocked_num_paths": 3,
            "stations": [
                {
                    "id": "s0",
                    "position": (100, 200),
                    "shape_type": "circle",
                    "passenger_count": 4,
                },
                {
                    "id": "s1",
                    "position": [300.5, 400.25],
                    "shape_type": "triangle",
                    "passenger_count": 1,
                },
            ],
            "paths": [
                {"id": "p0", "station_ids": ["s0", "s1"], "loop": False}
            ],
            "metros": [{"id": "m0", "path_id": "p0"}],
            "fleet": {"locomotives_available": 2, "carriages_available": 1},
        }
    }


def test_problem_contract_projects_public_observation_without_mutation() -> None:
    observation = _observation()
    before = copy.deepcopy(observation)

    state = state_from_observation(observation)

    assert observation == before
    assert state.problem_id == PROBLEM_ID
    assert state.contract_version == PROBLEM_CONTRACT_VERSION
    assert state.time_ms == 12_500
    assert state.deliveries == 7
    assert state.line_credits == 2
    assert state.unlocked_line_count == 3
    assert state.stations[0].x == 100.0
    assert state.stations[1].y == 400.25
    assert state.lines[0].station_ids == ("s0", "s1")
    assert state.vehicles[0].path_id == "p0"
    assert state.fleet.locomotives_available == 2
    assert state.served_station_ids == frozenset({"s0", "s1"})
    assert state.station_by_id["s1"].shape == "triangle"


def test_problem_contract_marks_missing_line_visibility_as_unknown() -> None:
    observation = _observation()
    observation["structured"].pop("unlocked_num_paths")

    state = state_from_observation(observation)

    assert state.unlocked_line_count is None


def test_problem_contract_rejects_malformed_station_position() -> None:
    observation = _observation()
    observation["structured"]["stations"][0]["position"] = [1]

    with pytest.raises(ValueError, match="invalid position"):
        state_from_observation(observation)
