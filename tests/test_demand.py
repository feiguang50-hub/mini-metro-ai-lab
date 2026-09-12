import math
import unittest

from metro_lab.demand import (
    DEMAND_CONTRACT_VERSION,
    DemandNode,
    ODDemandMatrix,
    ODFlow,
    explicit_od_matrix,
    synthetic_gravity_od,
)


class ExplicitODDemandTests(unittest.TestCase):
    def test_explicit_matrix_is_directional_and_sparse(self):
        matrix = explicit_od_matrix(
            ("A", "B", "C"),
            (
                ODFlow("A", "B", 12.0),
                ODFlow("B", "A", 3.0),
                ODFlow("C", "A", 5.0),
            ),
        )
        self.assertEqual(matrix.flow("A", "B"), 12.0)
        self.assertEqual(matrix.flow("B", "A"), 3.0)
        self.assertEqual(matrix.flow("A", "C"), 0.0)
        self.assertEqual(matrix.outbound("A"), 12.0)
        self.assertEqual(matrix.inbound("A"), 8.0)
        self.assertEqual(matrix.total_trips, 20.0)
        self.assertEqual(matrix.public()["contract_version"], DEMAND_CONTRACT_VERSION)

    def test_matrix_rejects_duplicate_unknown_and_self_pairs(self):
        with self.assertRaisesRegex(ValueError, "self-loop"):
            ODFlow("A", "A", 1.0)
        with self.assertRaisesRegex(ValueError, "unknown station"):
            ODDemandMatrix(
                station_ids=("A", "B"),
                flows=(ODFlow("A", "C", 1.0),),
            )
        with self.assertRaisesRegex(ValueError, "duplicate OD pair"):
            ODDemandMatrix(
                station_ids=("A", "B"),
                flows=(ODFlow("A", "B", 1.0), ODFlow("A", "B", 2.0)),
            )

    def test_flow_rejects_non_positive_or_non_finite_demand(self):
        for value in (0.0, -1.0, math.inf, math.nan):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ODFlow("A", "B", value)

    def test_synthetic_generator_is_seed_reproducible_and_normalized(self):
        nodes = (
            DemandNode("A", 0.0, 0.0, production_weight=1.4, attraction_weight=0.8),
            DemandNode("B", 1.0, 0.0, production_weight=0.8, attraction_weight=1.5),
            DemandNode("C", 0.0, 2.0),
            DemandNode("D", 3.0, 1.0),
        )
        first = synthetic_gravity_od(nodes, seed=2026, total_trips=600.0, density=0.7)
        second = synthetic_gravity_od(nodes, seed=2026, total_trips=600.0, density=0.7)
        other = synthetic_gravity_od(nodes, seed=2027, total_trips=600.0, density=0.7)

        self.assertEqual(first, second)
        self.assertNotEqual(first.flows, other.flows)
        self.assertAlmostEqual(first.total_trips, 600.0)
        self.assertEqual(first.source, "synthetic-gravity-v1")
        self.assertEqual(first.seed, 2026)
        self.assertTrue(all(flow.origin_id != flow.destination_id for flow in first.flows))

    def test_synthetic_generator_does_not_require_symmetric_flows(self):
        nodes = (
            DemandNode("A", 0.0, 0.0),
            DemandNode("B", 1.0, 0.0),
            DemandNode("C", 2.0, 0.0),
        )
        matrix = synthetic_gravity_od(nodes, seed=7, density=1.0)
        directional_pairs = [
            (matrix.flow("A", "B"), matrix.flow("B", "A")),
            (matrix.flow("A", "C"), matrix.flow("C", "A")),
            (matrix.flow("B", "C"), matrix.flow("C", "B")),
        ]
        self.assertTrue(any(forward != reverse for forward, reverse in directional_pairs))


if __name__ == "__main__":
    unittest.main()
