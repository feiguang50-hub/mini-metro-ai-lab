import unittest

from metro_lab.assignment import AssignmentLine, assign_passengers
from metro_lab.demand import DemandNode, ODFlow, explicit_od_matrix


class PassengerAssignmentV1Tests(unittest.TestCase):
    def setUp(self):
        self.nodes = (
            DemandNode("A", 0.0, 0.0),
            DemandNode("B", 1.0, 0.0),
            DemandNode("C", 2.0, 0.0),
            DemandNode("E", 0.0, 10.0),
            DemandNode("Z", 10.0, 10.0),
        )

    def test_direct_assignment_reports_station_line_and_edge_loads(self):
        demand = explicit_od_matrix(("A", "B", "C"), (ODFlow("A", "C", 12.0),))
        result = assign_passengers(
            demand,
            self.nodes,
            (AssignmentLine("red", ("A", "B", "C")),),
        )

        assigned = result.assignments[0]
        self.assertTrue(assigned.served)
        self.assertTrue(assigned.direct)
        self.assertEqual(assigned.transfers, 0)
        self.assertEqual(assigned.station_path, ("A", "B", "C"))
        self.assertEqual(assigned.line_path, ("red",))
        self.assertAlmostEqual(assigned.ride_distance, 2.0)
        self.assertAlmostEqual(assigned.generalized_cost, 2.0)
        self.assertEqual(result.direct_trips, 12.0)
        self.assertEqual(result.transfer_trips, 0.0)
        self.assertEqual(result.line_loads[0].line_id, "red")
        self.assertEqual(result.line_loads[0].trips, 12.0)
        self.assertEqual(
            {(edge.from_station_id, edge.to_station_id, edge.trips) for edge in result.edge_loads},
            {("A", "B", 12.0), ("B", "C", 12.0)},
        )

    def test_transfer_penalty_changes_route_choice(self):
        demand = explicit_od_matrix(("A", "B", "C", "E"), (ODFlow("A", "C", 20.0),))
        lines = (
            AssignmentLine("detour", ("A", "E", "C")),
            AssignmentLine("red", ("A", "B")),
            AssignmentLine("blue", ("B", "C")),
        )

        low_penalty = assign_passengers(demand, self.nodes, lines, transfer_penalty=5.0)
        high_penalty = assign_passengers(demand, self.nodes, lines, transfer_penalty=30.0)

        low = low_penalty.assignments[0]
        high = high_penalty.assignments[0]
        self.assertEqual(low.line_path, ("red", "blue"))
        self.assertEqual(low.transfers, 1)
        self.assertAlmostEqual(low.ride_distance, 2.0)
        self.assertAlmostEqual(low.generalized_cost, 7.0)

        self.assertEqual(high.line_path, ("detour",))
        self.assertEqual(high.transfers, 0)
        self.assertGreater(high.ride_distance, 20.0)
        self.assertAlmostEqual(high.generalized_cost, high.ride_distance)

    def test_unserved_demand_is_preserved_not_dropped(self):
        demand = explicit_od_matrix(("A", "C", "Z"), (ODFlow("A", "Z", 7.5), ODFlow("A", "C", 2.5)))
        result = assign_passengers(
            demand,
            self.nodes,
            (AssignmentLine("red", ("A", "B", "C")),),
        )

        self.assertEqual(result.total_trips, 10.0)
        self.assertEqual(result.served_trips, 2.5)
        self.assertEqual(result.unserved_trips, 7.5)
        unserved = result.assignments[0]
        self.assertFalse(unserved.served)
        self.assertIsNone(unserved.generalized_cost)
        self.assertEqual(unserved.station_path, ())

    def test_directional_edge_loads_remain_directional(self):
        demand = explicit_od_matrix(
            ("A", "B", "C"),
            (ODFlow("A", "C", 10.0), ODFlow("C", "A", 4.0)),
        )
        result = assign_passengers(
            demand,
            self.nodes,
            (AssignmentLine("red", ("A", "B", "C")),),
        )

        loads = {
            (edge.from_station_id, edge.to_station_id): edge.trips
            for edge in result.edge_loads
        }
        self.assertEqual(loads[("A", "B")], 10.0)
        self.assertEqual(loads[("B", "C")], 10.0)
        self.assertEqual(loads[("C", "B")], 4.0)
        self.assertEqual(loads[("B", "A")], 4.0)

    def test_loop_closing_edge_is_routable(self):
        demand = explicit_od_matrix(("A", "B", "C"), (ODFlow("C", "A", 3.0),))
        result = assign_passengers(
            demand,
            self.nodes,
            (AssignmentLine("ring", ("A", "B", "C"), loop=True),),
        )
        assigned = result.assignments[0]
        self.assertEqual(assigned.station_path, ("C", "A"))
        self.assertAlmostEqual(assigned.ride_distance, 2.0)
        self.assertEqual(assigned.transfers, 0)

    def test_network_validation_rejects_unknown_station_and_bad_penalty(self):
        demand = explicit_od_matrix(("A", "B"), (ODFlow("A", "B", 1.0),))
        with self.assertRaisesRegex(ValueError, "unknown stations"):
            assign_passengers(
                demand,
                self.nodes,
                (AssignmentLine("bad", ("A", "MISSING")),),
            )
        with self.assertRaisesRegex(ValueError, "transfer_penalty"):
            assign_passengers(
                demand,
                self.nodes,
                (AssignmentLine("red", ("A", "B")),),
                transfer_penalty=-1.0,
            )


if __name__ == "__main__":
    unittest.main()
