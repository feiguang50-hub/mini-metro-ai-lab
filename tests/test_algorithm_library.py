import unittest

from metro_lab.algorithms import (
    ALGORITHM_SPECS,
    DEFAULT_ALGORITHM_ID,
    algorithm_catalog,
    available_algorithm_ids,
    create_planner,
    get_algorithm_spec,
)


class AlgorithmLibraryTests(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [spec.id for spec in ALGORITHM_SPECS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_default_algorithm_is_available(self):
        self.assertIn(DEFAULT_ALGORITHM_ID, available_algorithm_ids())
        planner = create_planner(DEFAULT_ALGORITHM_ID)
        self.assertTrue(hasattr(planner, "act"))
        self.assertTrue(hasattr(planner, "reset"))

    def test_catalog_contains_planned_and_available_entries(self):
        catalog = algorithm_catalog()
        self.assertTrue(any(item["available"] for item in catalog))
        self.assertTrue(any(not item["available"] for item in catalog))
        self.assertTrue(all("factory" not in item for item in catalog))

    def test_planned_algorithm_cannot_be_started(self):
        planned = next(spec for spec in ALGORITHM_SPECS if not spec.available)
        with self.assertRaises(ValueError):
            create_planner(planned.id)
        self.assertEqual(get_algorithm_spec(planned.id).status, "planned")


if __name__ == "__main__":
    unittest.main()
