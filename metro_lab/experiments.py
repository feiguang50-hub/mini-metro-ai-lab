from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import ENGINE_COMMIT, ROOT
from .simulation import SIMULATION_PROTOCOL_VERSION

SCHEMA_VERSION = 1
DEFAULT_EXPERIMENT_ROOT = ROOT / "output" / "experiments"


def _artifact_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _artifact_jsonable(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _artifact_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_artifact_jsonable(item) for item in value]
    return str(value)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return slug or "run"


def _unique_run_dir(root: Path, base_name: str) -> Path:
    candidate = root / base_name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = root / f"{base_name}-{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


class ReplayWriter:
    """Write a versioned replay stream as gzip-compressed JSON Lines."""

    def __init__(self, path: Path, metadata: dict[str, Any]) -> None:
        self.path = Path(path)
        self.metadata = dict(metadata)
        self._handle = None
        self.frames = 0

    def start(self) -> "ReplayWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = gzip.open(self.path, "wt", encoding="utf-8")
        self._write(
            {
                "type": "header",
                "schema_version": SCHEMA_VERSION,
                "engine_commit": ENGINE_COMMIT,
                **_artifact_jsonable(self.metadata),
            }
        )
        return self

    def _write(self, payload: dict[str, Any]) -> None:
        if self._handle is None:
            raise RuntimeError("replay writer is not started")
        self._handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self._handle.write("\n")

    def write_frame(
        self,
        *,
        time_ms: int,
        game: dict[str, Any],
        decision: dict[str, Any],
        action_ok: bool,
        kind: str,
    ) -> None:
        self._write(
            {
                "type": "frame",
                "time_ms": int(time_ms),
                "kind": str(kind),
                "action_ok": bool(action_ok),
                "decision": _artifact_jsonable(decision),
                "game": _artifact_jsonable(game),
            }
        )
        self.frames += 1

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "ReplayWriter":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@dataclass(frozen=True)
class ExperimentArtifacts:
    run_id: str
    run_dir: Path
    replay_dir: Path
    config: dict[str, Any]

    @classmethod
    def create(
        cls,
        output_root: Path,
        *,
        algorithms: Iterable[str],
        seeds: Iterable[int],
        minutes: float,
        dt_ms: int,
        replay_sample_ms: int,
    ) -> "ExperimentArtifacts":
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        algorithm_ids = [str(item) for item in algorithms]
        seed_values = [int(item) for item in seeds]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        label = "-vs-".join(_safe_slug(item) for item in algorithm_ids[:3]) or "arena"
        if len(algorithm_ids) > 3:
            label += f"-plus{len(algorithm_ids) - 3}"
        run_id = f"{timestamp}-{label}"
        run_dir = _unique_run_dir(output_root, run_id)
        run_id = run_dir.name
        replay_dir = run_dir / "replays"
        replay_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "schema_version": SCHEMA_VERSION,
            "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "engine_commit": ENGINE_COMMIT,
            "algorithms": algorithm_ids,
            "seeds": seed_values,
            "minutes": float(minutes),
            "dt_ms": int(dt_ms),
            "replay_sample_ms": int(replay_sample_ms),
        }
        (run_dir / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cls(run_id=run_id, run_dir=run_dir, replay_dir=replay_dir, config=config)

    def replay_path(self, algorithm: str, seed: int) -> Path:
        return self.replay_dir / f"{_safe_slug(algorithm)}--seed-{int(seed)}.jsonl.gz"

    def finalize(self, results: Iterable[Any], summaries: Iterable[Any]) -> None:
        result_rows = [_artifact_jsonable(item) for item in results]
        summary_rows = [_artifact_jsonable(item) for item in summaries]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
            "run_id": self.run_id,
            "config": self.config,
            "results": result_rows,
            "summaries": summary_rows,
        }
        (self.run_dir / "results.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._write_csv(result_rows)
        self._write_summary(summary_rows)

    def _write_csv(self, rows: list[dict[str, Any]]) -> None:
        path = self.run_dir / "episodes.csv"
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fields = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _write_summary(self, rows: list[dict[str, Any]]) -> None:
        lines = [
            f"# Arena Experiment · {self.run_id}",
            "",
            f"- Engine: `{ENGINE_COMMIT}`",
            f"- Simulation protocol: `v{SIMULATION_PROTOCOL_VERSION}`",
            f"- Algorithms: {', '.join(f'`{item}`' for item in self.config['algorithms'])}",
            f"- Seeds: {', '.join(str(item) for item in self.config['seeds'])}",
            f"- Budget: {self.config['minutes']} min / seed",
            f"- Step: {self.config['dt_ms']} ms",
            "",
            "## Ranking",
            "",
            "| Algorithm | Deliveries | D/min | Avg waiting | Peak station | Fleet load | Game over | Invalid rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                "| {algorithm} | {mean_deliveries} | {mean_deliveries_per_minute} | "
                "{mean_waiting_passengers} | {mean_peak_station_queue} | {mean_fleet_load_pct:.1f}% | "
                "{game_over_rate:.1%} | {invalid_action_rate:.1%} |".format(
                    algorithm=row.get("algorithm", "?"),
                    mean_deliveries=row.get("mean_deliveries", 0),
                    mean_deliveries_per_minute=row.get("mean_deliveries_per_minute", 0),
                    mean_waiting_passengers=row.get("mean_waiting_passengers", 0),
                    mean_peak_station_queue=row.get("mean_peak_station_queue", 0),
                    mean_fleet_load_pct=float(row.get("mean_fleet_load_pct", 0)),
                    game_over_rate=float(row.get("game_over_rate", 0)),
                    invalid_action_rate=float(row.get("invalid_action_rate", 0)),
                )
            )
        lines.extend(
            [
                "",
                "## Metric notes",
                "",
                "- `Avg waiting`: time-weighted passengers waiting at stations.",
                "- `Peak station`: worst single-station queue observed in an episode, averaged across seeds.",
                "- `Fleet load`: time-weighted passenger occupancy while assigned capacity exists.",
                "- A rejected planner action still consumes the round as a noop under Simulation Protocol V2.",
                "",
                "## Files",
                "",
                "- `config.json`: exact experiment inputs and simulation protocol",
                "- `results.json`: machine-readable episode results and summaries",
                "- `episodes.csv`: one row per algorithm × seed episode",
                "- `replays/*.jsonl.gz`: sampled game states plus every non-noop decision",
                "",
                "> Runtime output lives under `output/` and is intentionally ignored by Git. Promote only representative experiments into the repository history.",
                "",
            ]
        )
        (self.run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
