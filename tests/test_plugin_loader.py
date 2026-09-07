from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metro_lab.algorithms import (
    _clear_external_algorithms_for_test,
    algorithm_catalog,
    available_algorithm_ids,
    create_planner,
)
from metro_lab.experiments import ExperimentArtifacts
from metro_lab.plugin_cli import consume_cli_plugins
from metro_lab.plugin_loader import PluginLoadError, load_plugin_file, load_plugins


def _plugin_code(algorithm_id: str) -> str:
    return f'''from metro_lab.action import NoOpAction, PlanningDecision
from metro_lab.plugin import AlgorithmMetadata

class ExternalAlgorithm:
    metadata = AlgorithmMetadata(
        id={algorithm_id!r},
        name="External Test",
        version="0.1",
        family="test",
        description="temporary external plugin",
    )

    def reset(self, state):
        self.reset_time = state.time_ms

    def act(self, state):
        return PlanningDecision(NoOpAction(), "external", f"t={{state.time_ms}}")

PLUGIN_FACTORY = ExternalAlgorithm
'''


def _minimal_observation() -> dict:
    return {
        "structured": {
            "time_ms": 123,
            "stations": [],
            "paths": [],
            "metros": [],
            "fleet": {
                "locomotives_available": 0,
                "carriages_available": 0,
            },
        }
    }


class ExternalPluginLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        _clear_external_algorithms_for_test()

    def tearDown(self) -> None:
        _clear_external_algorithms_for_test()

    def test_external_file_enters_same_algorithm_library_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "external.py"
            path.write_text(_plugin_code("external-test"), encoding="utf-8")

            loaded = load_plugin_file(path)

            self.assertEqual(loaded.spec.id, "external-test")
            self.assertEqual(loaded.spec.status, "external")
            self.assertEqual(loaded.spec.source_name, "external.py")
            self.assertEqual(
                loaded.spec.source_sha256,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            self.assertIn("external-test", available_algorithm_ids())
            public = next(
                item for item in algorithm_catalog() if item["id"] == "external-test"
            )
            self.assertEqual(public["status"], "external")
            self.assertEqual(public["source_sha256"], loaded.spec.source_sha256)

            planner = create_planner("external-test")
            observation = _minimal_observation()
            planner.reset(observation)
            decision = planner.act(observation)
            self.assertEqual(decision.action, {"type": "noop"})
            self.assertEqual(decision.title, "external")
            self.assertEqual(decision.detail, "t=123")

    def test_external_source_hash_is_frozen_into_experiment_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_path = root / "artifact_plugin.py"
            plugin_path.write_text(_plugin_code("external-artifact"), encoding="utf-8")
            loaded = load_plugin_file(plugin_path)

            artifacts = ExperimentArtifacts.create(
                root / "output",
                algorithms=["external-artifact"],
                seeds=[42],
                minutes=1.0,
                dt_ms=100,
                replay_sample_ms=1000,
            )
            config = json.loads(
                (artifacts.run_dir / "config.json").read_text(encoding="utf-8")
            )

            self.assertEqual(config["algorithm_specs"][0]["id"], "external-artifact")
            self.assertEqual(
                config["algorithm_specs"][0]["source_name"],
                "artifact_plugin.py",
            )
            self.assertEqual(
                config["algorithm_specs"][0]["source_sha256"],
                loaded.spec.source_sha256,
            )

    def test_builtin_algorithm_ids_are_reserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "collision.py"
            path.write_text(_plugin_code("greedy-v1"), encoding="utf-8")

            with self.assertRaisesRegex(PluginLoadError, "reserved algorithm id"):
                load_plugin_file(path)

    def test_plugin_must_export_factory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.py"
            path.write_text("VALUE = 1\n", encoding="utf-8")

            with self.assertRaisesRegex(PluginLoadError, "PLUGIN_FACTORY"):
                load_plugin_file(path)

    def test_factory_failure_is_reported_as_plugin_load_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad_factory.py"
            path.write_text(
                "def PLUGIN_FACTORY():\n    raise RuntimeError('factory boom')\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PluginLoadError, "plugin factory failed"):
                load_plugin_file(path)

    def test_empty_plugin_directory_is_rejected_early(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(PluginLoadError, "contains no visible"):
                load_plugins([Path(temp)])

    def test_directory_loading_is_shallow_sorted_and_skips_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "b.py").write_text(_plugin_code("external-b"), encoding="utf-8")
            (root / "a.py").write_text(_plugin_code("external-a"), encoding="utf-8")
            (root / "_helper.py").write_text("raise RuntimeError('must not run')\n", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "c.py").write_text(_plugin_code("external-c"), encoding="utf-8")

            loaded = load_plugins([root])

            self.assertEqual([item.path.name for item in loaded], ["a.py", "b.py"])
            self.assertEqual([item.spec.id for item in loaded], ["external-a", "external-b"])
            self.assertNotIn("external-c", available_algorithm_ids())

    def test_cli_consumes_plugin_argument_before_delegating(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cli_plugin.py"
            path.write_text(_plugin_code("external-cli"), encoding="utf-8")

            loaded, remaining = consume_cli_plugins(
                ["--plugin", str(path), "--algorithms", "external-cli", "--minutes", "1"]
            )

            self.assertEqual([item.spec.id for item in loaded], ["external-cli"])
            self.assertEqual(
                remaining,
                ("--algorithms", "external-cli", "--minutes", "1"),
            )


if __name__ == "__main__":
    unittest.main()
