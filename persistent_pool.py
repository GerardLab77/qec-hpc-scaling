"""Measure fresh seeded batches decoded by one persistent process pool.

Separate filenames and schema keep these observations out of the original
single-dispatch analyser. No benchmarks execute when this module is imported.
"""
import argparse
import datetime as dt
import hashlib
import itertools
import json
import multiprocessing as mp
import os
import random
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Import first: this sets numerical-library thread limits before NumPy loads.
from qec_bench import bounds, circuit_for, hardware, seeded_data
import numpy as np
import psutil
import pymatching
import stim


def _initialise(dem, barrier):
    global _decoder, _rendezvous
    _decoder = pymatching.Matching.from_detector_error_model(
        stim.DetectorErrorModel(dem))
    _rendezvous = barrier


def _decode(task):
    path, lo, hi, warmup = task
    # Reopen for each task. All tasks finish and close mappings before the
    # parent overwrites this file with the next batch (also works on Windows).
    syn = np.load(path, mmap_mode="r")
    try:
        if warmup:
            _decoder.decode_batch(syn[lo:min(lo + 256, hi)])
        _rendezvous.wait(timeout=120)
        if warmup:
            return os.getpid()
        start = time.perf_counter()
        predicted = _decoder.decode_batch(syn[lo:hi])
        elapsed = time.perf_counter() - start
        return predicted, elapsed, os.getpid()
    finally:
        # No array views escape this function; predictions own their storage.
        syn._mmap.close()


def _positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def check_capacity(workers):
    try:
        visible = len(psutil.Process().cpu_affinity())
    except (AttributeError, NotImplementedError):
        visible = os.cpu_count() or 1
    allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", visible))
    if workers > min(visible, allocated):
        raise ValueError("workers exceed visible/allocated CPUs")


def _digest(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def measure_persistent(distance, rounds, p, shots, workers, batches, seed,
                       on_batch=None):
    """One fresh pool, N distinct seeded inputs, one synchronous batch at a time.

    workload_wall_s includes model/data generation, temporary input I/O,
    correctness instrumentation, callbacks and pool shutdown. It excludes the
    runner's final summary write. decode_service_s accounts only for setup +
    dispatches + shutdown; it is NOT an end-to-end streaming measurement.
    """
    for name, value in (("distance", distance), ("rounds", rounds),
                        ("shots", shots), ("workers", workers), ("batches", batches)):
        _positive(value, name)
    if type(seed) is not int or not 0 <= seed <= 2**64 - batches:
        raise ValueError("batch seeds must fit Stim's unsigned 64-bit range")
    partitions = bounds(shots, workers)
    check_capacity(workers)
    start_all = time.perf_counter()
    start = time.perf_counter()
    circuit = circuit_for(distance, rounds, p)
    dem = str(circuit.detector_error_model(decompose_errors=True))
    model_s = time.perf_counter() - start
    context = mp.get_context("spawn")
    records = []
    with tempfile.TemporaryDirectory(prefix="qec-persistent-",
                                     dir=os.environ.get("QEC_TMPDIR")) as tmp:
        path = str(Path(tmp) / "batch.npy")

        def prepare(index):
            start = time.perf_counter()
            syn, actual = seeded_data(circuit, shots, seed + index)
            sample_s = time.perf_counter() - start
            start = time.perf_counter()
            digest = _digest(syn, actual)
            hash_s = time.perf_counter() - start
            start = time.perf_counter()
            np.save(path, syn)
            write_s = time.perf_counter() - start
            return actual, digest, sample_s, hash_s, write_s

        prepared = prepare(0)
        tasks = [(path, lo, hi, False) for lo, hi in partitions]
        barrier = context.Barrier(workers)
        start = time.perf_counter()
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                   initializer=_initialise, initargs=(dem, barrier))
        try:
            warm_pids = list(pool.map(_decode, [(path, lo, hi, True)
                                               for lo, hi in partitions]))
            setup_s = time.perf_counter() - start
            if len(set(warm_pids)) != workers:
                raise RuntimeError("Not all workers participated in warmup")
            for index in range(batches):
                if index:
                    prepared = prepare(index)
                actual, input_hash, sample_s, hash_s, write_s = prepared
                start = time.perf_counter()
                chunks = list(pool.map(_decode, tasks))
                dispatch_s = time.perf_counter() - start
                start = time.perf_counter()
                pids = [chunk[2] for chunk in chunks]
                if set(pids) != set(warm_pids) or len(set(pids)) != workers:
                    raise RuntimeError("Persistent worker participation changed")
                predicted = np.concatenate([chunk[0] for chunk in chunks], axis=0)
                if predicted.shape != actual.shape:
                    raise RuntimeError("Invalid prediction shape")
                failures = int(np.count_nonzero(np.any(predicted != actual, axis=1)))
                prediction_hash = _digest(predicted)
                validation_s = time.perf_counter() - start
                row = dict(batch_index=index, batch_seed=seed + index,
                           shots=shots, input_sha256=input_hash,
                           prediction_sha256=prediction_hash, failures=failures,
                           sample_s=sample_s, input_hash_s=hash_s,
                           input_write_s=write_s, validation_s=validation_s,
                           dispatch_s=dispatch_s,
                           worker_decode_max_s=max(chunk[1] for chunk in chunks),
                           worker_pids=pids)
                records.append(row)
                if on_batch:
                    on_batch(row)
                # Release returned prediction arrays before the next dispatch.
                del chunks, predicted
        finally:
            start = time.perf_counter()
            pool.shutdown(wait=True, cancel_futures=True)
            shutdown_s = time.perf_counter() - start
    wall_s = time.perf_counter() - start_all
    dispatch_sum = sum(row["dispatch_s"] for row in records)
    service_s = setup_s + dispatch_sum + shutdown_s
    total_shots = shots * batches
    return dict(distance=distance, rounds=rounds, p=p, shots=shots,
                workers=workers, batches=batches, seed=seed,
                total_shots=total_shots, detectors=circuit.num_detectors,
                model_s=model_s, pool_setup_warmup_s=setup_s,
                pool_shutdown_s=shutdown_s, dispatch_sum_s=dispatch_sum,
                decode_service_s=service_s, workload_wall_s=wall_s,
                warmed_throughput_shots_s=total_shots / dispatch_sum,
                service_throughput_shots_s=total_shots / service_s,
                workload_throughput_shots_s=total_shots / wall_s,
                batch_records=records)


def cases_from(config):
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported persistent config schema")
    _positive(config.get("repetitions"), "repetitions")
    seed = config.get("seed")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    cases = []
    for exp in config["experiments"]:
        if not exp.get("name"):
            raise ValueError("Experiment needs a name")
        for d, n, w, b in itertools.product(exp["distances"], exp["shots"],
                                           exp["workers"], exp["batches"]):
            r = exp.get("rounds", d)
            for name, value in (("distance", d), ("rounds", r), ("shots", n),
                                ("workers", w), ("batches", b)):
                _positive(value, name)
            bounds(n, w)
            if d < 3 or d % 2 == 0 or not 0 <= exp["p"] < 0.5:
                raise ValueError("Invalid circuit parameters")
            cases.append(dict(experiment=exp["name"], distance=d, rounds=r,
                              p=exp["p"], shots=n, workers=w, batches=b))
    if not cases or len({tuple(c.items()) for c in cases}) != len(cases):
        raise ValueError("Empty or duplicate persistent cases")
    stride = max(c["batches"] for c in cases)
    if seed + config["repetitions"] * stride > 2**64:
        raise ValueError("Seed range exceeds unsigned 64-bit integers")
    controls = {(c["experiment"], c["distance"], c["rounds"], c["p"], c["shots"], c["batches"])
                for c in cases if c["workers"] == 1}
    for c in cases:
        if (c["experiment"], c["distance"], c["rounds"], c["p"], c["shots"], c["batches"]) not in controls:
            raise ValueError("Every persistent case needs a 1-worker baseline")
    return cases


def run(config_path, output="results/persistent", label="persistent"):
    raw = Path(config_path).read_bytes()
    config = json.loads(raw)
    cases = cases_from(config)
    check_capacity(max(c["workers"] for c in cases))
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = Path(output) / run_id
    destination.mkdir(parents=True)
    root = Path(__file__).resolve().parent
    try:
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                           text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"],
                                            text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    meta = dict(schema="qec-persistent-v1", run_id=run_id, label=label,
                config=config, config_sha256=hashlib.sha256(raw).hexdigest(),
                hardware=hardware(), git_revision=revision, git_dirty=dirty,
                expected_sessions=len(cases) * config["repetitions"],
                source_hashes={name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                               for name in ("persistent_pool.py", "qec_bench.py",
                                            "analyse_persistent.py")})
    (destination / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Results: {destination}", flush=True)
    rng = random.Random(config["seed"])
    stride = max(c["batches"] for c in cases)
    with (destination / "persistent_measurements.jsonl").open("w", encoding="utf-8") as summaries, \
         (destination / "persistent_batches.jsonl").open("w", encoding="utf-8") as batches:
        for repeat in range(config["repetitions"]):
            ordered = cases.copy()
            rng.shuffle(ordered)
            for index, case in enumerate(ordered):
                session_id = f"r{repeat}-c{index}"
                identity = dict(run_id=run_id, session_id=session_id,
                                repetition=repeat, **case)

                def save_batch(row):
                    batches.write(json.dumps(dict(identity, **row)) + "\n")
                    batches.flush()

                params = {k: v for k, v in case.items() if k != "experiment"}
                row = measure_persistent(**params, seed=config["seed"] + repeat * stride,
                                         on_batch=save_batch)
                row.pop("batch_records")
                summaries.write(json.dumps(dict(identity, **row)) + "\n")
                summaries.flush()
                print(f"rep={repeat} w={case['workers']} shots={case['shots']} "
                      f"batches={case['batches']} wall={row['workload_wall_s']:.3f}s "
                      f"service={row['decode_service_s']:.3f}s", flush=True)
    (destination / "COMPLETE").write_text("All configured sessions completed.\n", encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/persistent-smoke.json")
    parser.add_argument("--output", default="results/persistent")
    parser.add_argument("--label", default="persistent")
    args = parser.parse_args()
    run(args.config, args.output, args.label)
