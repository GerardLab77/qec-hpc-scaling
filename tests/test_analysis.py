"""Prevent misleading aggregation and speedup comparisons."""
import unittest
from analyse_results import paired_speedups, quartiles


class AnalysisTests(unittest.TestCase):
    def test_median_and_iqr(self):
        self.assertEqual(quartiles([1, 2, 3, 4, 100]), (3, 2, 4))

    def test_speedup_rejects_different_input(self):
        base = dict(cohort="test", experiment="strong_scaling", distance=3,
                    rounds=3, p=0.005, shots=1000, repetition=0, seed=1,
                    input_sha256="a", prediction_sha256="b", failures=2, dispatch_s=1, workers=1)
        other = dict(base, workers=2, input_sha256="different")
        with self.assertRaisesRegex(ValueError, "comparability failure"):
            paired_speedups([base, other])

    def test_speedup_uses_serial_baseline(self):
        base = dict(cohort="test", experiment="strong_scaling", distance=3,
                    rounds=3, p=0.005, shots=1000, repetition=0, seed=1,
                    input_sha256="a", prediction_sha256="b", failures=2, dispatch_s=2, workers=1)
        result = paired_speedups([base, dict(base, workers=2, dispatch_s=1.25)])
        self.assertAlmostEqual(result[1]["speedup"], 1.6)
        self.assertAlmostEqual(result[1]["efficiency"], 0.8)


if __name__ == "__main__":
    unittest.main()
