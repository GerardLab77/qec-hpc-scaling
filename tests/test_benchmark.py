"""Tests guard decoding correctness and strong-scaling comparability."""
import unittest
import numpy as np
import pymatching
from qec_bench import bounds, circuit_for, measure, seeded_data


class BenchmarkTests(unittest.TestCase):
    def test_partition_covers_uneven_batch(self):
        ranges = bounds(1003, 4)
        self.assertEqual([i for lo, hi in ranges for i in range(lo, hi)], list(range(1003)))

    def test_noiseless_memory(self):
        c = circuit_for(3, 3, 0)
        syn, actual = seeded_data(c, 200, 7)
        m = pymatching.Matching.from_detector_error_model(c.detector_error_model(decompose_errors=True))
        np.testing.assert_array_equal(m.decode_batch(syn), actual)

    def test_batch_matches_single_shot(self):
        c = circuit_for(3, 3, 0.005)
        syn, _ = seeded_data(c, 200, 8)
        m = pymatching.Matching.from_detector_error_model(c.detector_error_model(decompose_errors=True))
        np.testing.assert_array_equal(m.decode_batch(syn), np.array([m.decode(x) for x in syn]))

    def test_parallel_matches_serial(self):
        a = measure(3, 3, 0.005, 1003, 1, 9)
        b = measure(3, 3, 0.005, 1003, 2, 9)
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(a["prediction_sha256"], b["prediction_sha256"])
        self.assertEqual(a["failures"], b["failures"])
        self.assertGreater(a["dispatch_s"], 0)


if __name__ == "__main__":
    unittest.main()
