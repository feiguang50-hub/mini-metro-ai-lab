import unittest
from types import SimpleNamespace

from metro_lab.pressure import passenger_pressure


def env_with_waits(*station_waits, max_wait=40_000, threshold=2):
    stations = [
        SimpleNamespace(passengers=[SimpleNamespace(wait_ms=wait) for wait in waits])
        for waits in station_waits
    ]
    mediator = SimpleNamespace(
        stations=stations,
        passenger_max_wait_time_ms=max_wait,
        overdue_passenger_threshold=threshold,
    )
    return SimpleNamespace(mediator=mediator)


class PassengerPressureTests(unittest.TestCase):
    def test_empty_network_has_zero_risk(self):
        pressure = passenger_pressure(env_with_waits(()))
        self.assertEqual(pressure.risk_pct, 0)
        self.assertEqual(pressure.waiting_passengers, 0)
        self.assertEqual(pressure.overdue_passengers, 0)

    def test_risk_uses_top_threshold_wait_clocks(self):
        pressure = passenger_pressure(env_with_waits((40_000,), (20_000,)))
        self.assertEqual(pressure.risk_pct, 75)
        self.assertEqual(pressure.max_wait_ms, 40_000)
        self.assertEqual(pressure.overdue_passengers, 1)
        self.assertEqual(pressure.at_risk_passengers, 1)

    def test_two_overdue_passengers_across_stations_reach_game_over_risk(self):
        pressure = passenger_pressure(env_with_waits((40_000,), (41_000,)))
        self.assertEqual(pressure.risk_pct, 100)
        self.assertEqual(pressure.overdue_passengers, 2)
        self.assertEqual(pressure.waiting_passengers, 2)

    def test_thirty_seconds_is_at_risk_for_forty_second_limit(self):
        pressure = passenger_pressure(env_with_waits((30_000,), (0,)))
        self.assertEqual(pressure.at_risk_wait_ms, 30_000)
        self.assertEqual(pressure.at_risk_passengers, 1)
        self.assertEqual(pressure.overdue_passengers, 0)


if __name__ == "__main__":
    unittest.main()
