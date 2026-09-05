import unittest

from metro_lab.metrics import EpisodeTelemetry


def observation(*, time_ms=0, waiting=(0, 0), onboard=0, capacity=0, paths=1, locos=1, carriages=0):
    passengers = [f"p{i}" for i in range(onboard)]
    metros = []
    if capacity > 0:
        metros.append({"passenger_ids": passengers, "capacity": capacity})
    return {
        "structured": {
            "time_ms": time_ms,
            "stations": [
                {"passenger_count": count}
                for count in waiting
            ],
            "paths": [{} for _ in range(paths)],
            "metros": metros,
            "fleet": {
                "locomotives_assigned": locos,
                "carriages_assigned": carriages,
            },
        }
    }


class EpisodeTelemetryTests(unittest.TestCase):
    def test_time_weighted_waiting_and_fleet_load(self):
        telemetry = EpisodeTelemetry()
        telemetry.observe_initial(observation(waiting=(1, 2), onboard=1, capacity=4))
        telemetry.record_transition(
            observation(time_ms=1000, waiting=(2, 4), onboard=2, capacity=4, paths=2, locos=2, carriages=1),
            elapsed_ms=1000,
        )
        telemetry.record_transition(
            observation(time_ms=2000, waiting=(0, 2), onboard=3, capacity=4, paths=2, locos=2, carriages=1),
            elapsed_ms=1000,
        )

        self.assertAlmostEqual(telemetry.average_waiting_passengers, 4.0)
        self.assertAlmostEqual(telemetry.waiting_passenger_seconds, 8.0)
        self.assertAlmostEqual(telemetry.average_fleet_load_pct, 62.5)
        self.assertEqual(telemetry.peak_network_waiting, 6)
        self.assertEqual(telemetry.peak_station_queue, 4)
        self.assertEqual(telemetry.max_paths, 2)
        self.assertEqual(telemetry.max_locomotives_assigned, 2)
        self.assertEqual(telemetry.max_carriages_assigned, 1)

    def test_action_counters_distinguish_topology(self):
        telemetry = EpisodeTelemetry()
        for action in ("noop", "replace_path", "assign_locomotive", "create_path"):
            telemetry.record_action(action)
        self.assertEqual(telemetry.non_noop_actions, 3)
        self.assertEqual(telemetry.topology_actions, 2)


if __name__ == "__main__":
    unittest.main()
