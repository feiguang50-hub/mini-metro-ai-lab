import unittest

from metro_lab.arena import EpisodeResult, run_episode, summarize
from metro_lab.config import ENGINE_SRC


class ArenaPureTests(unittest.TestCase):
    def test_summary_ranks_by_mean_deliveries(self):
        results = [
            EpisodeResult("a", 1, 10, 0, 1000, 10, False, 0),
            EpisodeResult("a", 2, 20, 0, 1000, 10, False, 1),
            EpisodeResult("b", 1, 8, 0, 1000, 10, True, 0),
            EpisodeResult("b", 2, 9, 0, 1000, 10, True, 0),
        ]
        summaries = summarize(results)
        self.assertEqual([item.algorithm for item in summaries], ["a", "b"])
        self.assertEqual(summaries[0].mean_deliveries, 15.0)
        self.assertEqual(summaries[0].invalid_actions, 1)
        self.assertEqual(summaries[1].game_over_rate, 1.0)


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class ArenaEngineTests(unittest.TestCase):
    def test_short_episode_uses_real_engine(self):
        result = run_episode("greedy-v1", 42, minutes=0.02)
        self.assertEqual(result.algorithm, "greedy-v1")
        self.assertEqual(result.seed, 42)
        self.assertGreater(result.steps, 0)
        self.assertGreater(result.simulated_ms, 0)
        self.assertGreaterEqual(result.deliveries, 0)


if __name__ == "__main__":
    unittest.main()
