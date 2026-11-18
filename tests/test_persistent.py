"""Persistent workers, fresh inputs, complete campaigns and paired correctness."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from persistent_pool import cases_from, measure_persistent, check_capacity, _digest
from qec_bench import circuit_for, seeded_data
from analyse_persistent import validate, paired_speedups
import pymatching


def config():
    return dict(schema_version=1, seed=37, repetitions=1, experiments=[dict(
        name="persistent", distances=[3], rounds=3, p=.005,
        shots=[1003], workers=[1, 2], batches=[3])])


class PersistentConfigTests(unittest.TestCase):
    def test_rejects_invalid_and_duplicate_cases(self):
        for field, values in (("batches", [0]), ("batches", [True]),
                              ("batches", [1, 1]), ("workers", [2]),
                              ("workers", [1004]), ("shots", [1.5])):
            c = config()
            c["experiments"][0][field] = values
            with self.subTest(field=field, values=values), self.assertRaises(ValueError):
                cases_from(c)

    def test_main_matrix_size(self):
        root = Path(__file__).resolve().parents[1]
        c = json.loads((root / "configs/persistent-stanage.json").read_text())
        cases = cases_from(c)
        self.assertEqual(len(cases) * c["repetitions"], 150)
        self.assertEqual(sum(r["batches"] for r in cases) * c["repetitions"], 5550)

    def test_capacity_honours_allocation(self):
        with patch.dict(os.environ, {"SLURM_CPUS_PER_TASK": "1"}):
            with self.assertRaisesRegex(ValueError, "allocated CPUs"):
                check_capacity(2)

    def test_rejects_seed_overflow(self):
        c = config()
        c["seed"] = 2**64 - 1
        with self.assertRaisesRegex(ValueError, "Seed range"):
            cases_from(c)


class PersistentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            check_capacity(2)
        except ValueError as exc:
            raise unittest.SkipTest("Needs two allocated/visible CPUs") from exc
        cls.serial = measure_persistent(3, 3, .005, 1003, 1, 3, 37)
        cls.parallel = measure_persistent(3, 3, .005, 1003, 2, 3, 37)

    def test_fresh_batches_match_direct_decoder_and_serial(self):
        circuit = circuit_for(3, 3, .005)
        decoder = pymatching.Matching.from_detector_error_model(
            circuit.detector_error_model(decompose_errors=True))
        hashes = set()
        pids = set(self.parallel["batch_records"][0]["worker_pids"])
        for index, (serial, parallel) in enumerate(zip(
                self.serial["batch_records"], self.parallel["batch_records"])):
            syn, actual = seeded_data(circuit, 1003, 37 + index)
            predicted = decoder.decode_batch(syn)
            self.assertEqual(parallel["input_sha256"], _digest(syn, actual))
            self.assertEqual(parallel["prediction_sha256"], _digest(predicted))
            for field in ("input_sha256", "prediction_sha256", "failures"):
                self.assertEqual(serial[field], parallel[field])
            self.assertEqual(set(parallel["worker_pids"]), pids)
            hashes.add(parallel["input_sha256"])
        self.assertEqual(len(hashes), 3)
        self.assertEqual(len(pids), 2)

    def fixture(self, root):
        meta = dict(schema="qec-persistent-v1", run_id="test", config=config())
        (root / "metadata.json").write_text(json.dumps(meta))
        (root / "COMPLETE").write_text("done")
        sessions, batches = [], []
        for index, result in enumerate((self.serial, self.parallel)):
            row = copy.deepcopy(result)
            records = row.pop("batch_records")
            identity = dict(run_id="test", session_id=str(index), repetition=0,
                            experiment="persistent")
            sessions.append(dict(row, **identity))
            for batch in records:
                batches.append(dict(batch, **identity, distance=3, rounds=3,
                                    p=.005, workers=row["workers"], batches=3))
        for name, rows in (("persistent_measurements", sessions), ("persistent_batches", batches)):
            (root / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_complete_campaign_and_all_timing_baselines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            rows, batches = validate(root)
            pairs = paired_speedups(rows, batches)
            self.assertEqual(len(pairs), 2)
            for metric in ("warmed", "service", "workload"):
                self.assertEqual(pairs[0][metric + "_speedup"], 1)
            # Corruption of predictions must fail even if timings look plausible.
            batches["1"][1]["prediction_sha256"] = "wrong"
            with self.assertRaisesRegex(ValueError, "mismatch"):
                paired_speedups(rows, batches)

    def test_rejects_missing_batches_and_completion_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root / "persistent_batches.jsonl"
            path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "Missing or duplicate batches"):
                validate(root)
            (root / "COMPLETE").unlink()
            with self.assertRaisesRegex(ValueError, "complete persistent"):
                validate(root)

    def test_rejects_duplicate_sessions_and_missing_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            rows, batches = validate(root)
            with self.assertRaisesRegex(ValueError, "baseline"):
                paired_speedups([rows[1]], batches)
            path = root / "persistent_measurements.jsonl"
            with path.open("a") as f:
                f.write(json.dumps(rows[0]) + "\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validate(root)


if __name__ == "__main__":
    unittest.main()
