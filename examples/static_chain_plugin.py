from metro_lab.assignment import AssignmentLine
from metro_lab.static_od import StaticAlgorithmMetadata


class ExampleStaticChain:
    metadata = StaticAlgorithmMetadata(
        id="example-static-chain",
        name="Example Static Chain",
        version="1.0",
        description="Minimal external Static OD plugin example.",
    )

    def design(self, instance):
        station_ids = tuple(node.id for node in instance.nodes)
        width = instance.budget.max_stations_per_line
        lines = []
        cursor = 0
        index = 1
        while cursor < len(station_ids) - 1:
            end = min(len(station_ids), cursor + width)
            lines.append(AssignmentLine(f"ext-{index}", station_ids[cursor:end]))
            if end == len(station_ids):
                break
            cursor = end - 1
            index += 1
        return tuple(lines)


def STATIC_PLUGIN_FACTORY():
    return ExampleStaticChain()
