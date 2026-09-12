import tempfile
import unittest
from pathlib import Path

from metro_lab.static_od import STATIC_ALGORITHMS, run_static_algorithm, synthetic_static_od_instance
from metro_lab.static_plugin_cli import consume_static_cli_plugins
from metro_lab.static_plugin_loader import StaticPluginLoadError, load_static_plugin_file


PLUGIN_SOURCE = '''
from metro_lab.assignment import AssignmentLine
from metro_lab.static_od import StaticAlgorithmMetadata

class TempStaticPlugin:
    metadata = StaticAlgorithmMetadata(
        id="temp-static-plugin",
        name="Temp Static Plugin",
        version="1.0",
        description="test plugin",
    )

    def design(self, instance):
        station_ids = tuple(node.id for node in instance.nodes)
        width = instance.budget.max_stations_per_line
        first = station_ids[:width]
        second = station_ids[width - 1:]
        lines = [AssignmentLine("temp-1", first)]
        if len(second) >= 2:
            lines.append(AssignmentLine("temp-2", second))
        return tuple(lines)

def STATIC_PLUGIN_FACTORY():
    return TempStaticPlugin()
'''


class StaticPluginLoaderTests(unittest.TestCase):
    def test_external_static_plugin_loads_and_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "temp_static.py"
            path.write_text(PLUGIN_SOURCE, encoding="utf-8")
            loaded = load_static_plugin_file(path)
            self.assertEqual(loaded.metadata.id, "temp-static-plugin")
            self.assertEqual(len(loaded.source_sha256), 64)
            self.assertIn("temp-static-plugin", STATIC_ALGORITHMS.ids())
            result = run_static_algorithm(
                synthetic_static_od_instance(123),
                "temp-static-plugin",
            )
            self.assertEqual(result.algorithm, "temp-static-plugin")
            self.assertGreater(result.coverage_rate, 0.0)

    def test_cli_consumes_plugin_before_static_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cli_static.py"
            source = PLUGIN_SOURCE.replace("temp-static-plugin", "cli-static-plugin")
            path.write_text(source, encoding="utf-8")
            loaded, remaining = consume_static_cli_plugins(
                ["--plugin", str(path), "--algorithms", "cli-static-plugin", "--no-save"]
            )
            self.assertEqual([item.metadata.id for item in loaded], ["cli-static-plugin"])
            self.assertEqual(remaining, ["--algorithms", "cli-static-plugin", "--no-save"])

    def test_rejects_missing_static_factory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.py"
            path.write_text("VALUE = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(StaticPluginLoadError, "STATIC_PLUGIN_FACTORY"):
                load_static_plugin_file(path)


if __name__ == "__main__":
    unittest.main()
