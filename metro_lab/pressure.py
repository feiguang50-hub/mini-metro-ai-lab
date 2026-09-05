from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AT_RISK_FRACTION = 0.75


@dataclass(frozen=True)
class PassengerPressure:
    """Passenger waiting pressure aligned with the pinned engine's game-over rule."""

    waiting_passengers: int
    at_risk_passengers: int
    overdue_passengers: int
    max_wait_ms: int
    passenger_max_wait_time_ms: int
    overdue_passenger_threshold: int
    risk_pct: int

    @property
    def at_risk_wait_ms(self) -> int:
        return round(self.passenger_max_wait_time_ms * AT_RISK_FRACTION)


def passenger_pressure(env: Any) -> PassengerPressure:
    """Read live station passengers and convert their wait clocks to 0..100 risk.

    The engine ends the game when at least ``overdue_passenger_threshold``
    station passengers each reach ``passenger_max_wait_time_ms``. Risk therefore
    averages the normalized wait progress of the N most endangered passengers,
    where N is that threshold. This makes 100% line up with the actual failure
    condition instead of confusing station queue length with overdue count.
    """

    mediator = env.mediator
    max_wait = max(1, int(getattr(mediator, "passenger_max_wait_time_ms", 40_000)))
    overdue_threshold = max(1, int(getattr(mediator, "overdue_passenger_threshold", 2)))
    at_risk_wait = round(max_wait * AT_RISK_FRACTION)

    waits = [
        max(0, int(getattr(passenger, "wait_ms", 0)))
        for station in mediator.stations
        for passenger in station.passengers
    ]
    waits.sort(reverse=True)

    overdue = sum(wait >= max_wait for wait in waits)
    at_risk = sum(wait >= at_risk_wait for wait in waits)
    top = waits[:overdue_threshold]
    if len(top) < overdue_threshold:
        top.extend([0] * (overdue_threshold - len(top)))
    risk = round(
        sum(min(wait / max_wait, 1.0) for wait in top)
        / overdue_threshold
        * 100
    )

    return PassengerPressure(
        waiting_passengers=len(waits),
        at_risk_passengers=at_risk,
        overdue_passengers=overdue,
        max_wait_ms=max(waits, default=0),
        passenger_max_wait_time_ms=max_wait,
        overdue_passenger_threshold=overdue_threshold,
        risk_pct=max(0, min(100, risk)),
    )
