"""Explicit timing boundaries for offline Stim/PyMatching decoding."""
import hashlib
import importlib.metadata
import multiprocessing as mp
import os
import platform
import socket
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Set before numerical libraries load, including in spawn children.
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"

import numpy as np
import psutil
import pymatching
import stim


def circuit_for(distance, rounds, p):
    """Match QStone's noise channel, but parameterise the space-time graph."""
    if distance < 3 or distance % 2 == 0 or rounds < 1 or not 0 <= p < 0.5:
        raise ValueError("Require odd distance >=3, rounds >=1 and 0<=p<0.5")
    return stim.Circuit.generated(
        "surface_code:rotated_memory_x", distance=distance, rounds=rounds,
        after_clifford_depolarization=p,
    )


def bounds(shots, workers):
    if shots < workers or workers < 1:
        raise ValueError("Require shots >= workers >= 1")
    return [(shots * i // workers, shots * (i + 1) // workers)
            for i in range(workers)]


def seeded_data(circuit, shots, seed):
    return circuit.compile_detector_sampler(seed=seed).sample(
        shots=shots, separate_observables=True)


def _init_worker(dem, path, barrier):
    global _matching, _syn, _barrier
    _matching = pymatching.Matching.from_detector_error_model(stim.DetectorErrorModel(dem))
    _syn = np.load(path, mmap_mode="r")
    _barrier = barrier


def _decode_chunk(interval, warmup=False):
    lo, hi = interval
    # Each task must occupy a distinct worker before starting the batch.
    if warmup:
        _matching.decode_batch(_syn[lo:min(lo + 256, hi)])
    _barrier.wait(timeout=120)
    if warmup:
        return os.getpid()
    t0, c0 = time.perf_counter_ns(), time.process_time_ns()
    predictions = _matching.decode_batch(_syn[lo:hi])
    cpu_ns = time.process_time_ns() - c0
    wall_ns = time.perf_counter_ns() - t0
    # RSS is a snapshot after decoding, deliberately not labelled peak memory.
    return predictions, wall_ns / 1e9, cpu_ns / 1e9, psutil.Process().memory_info().rss, os.getpid()


def hardware():
    proc = psutil.Process()
    try:
        affinity = proc.cpu_affinity()
    except (AttributeError, NotImplementedError):
        affinity = None
    return {
        "hostname": socket.gethostname(), "platform": platform.platform(),
        "processor": platform.processor(), "python": sys.version,
        "logical_cpus": psutil.cpu_count(), "physical_cores": psutil.cpu_count(logical=False),
        "affinity": affinity, "ram_bytes": psutil.virtual_memory().total,
        "versions": {p: importlib.metadata.version(p) for p in
                     ("stim", "pymatching", "numpy", "scipy", "matplotlib", "psutil", "networkx")},
        "thread_environment": {k: os.environ[k] for k in
                               ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "slurm": {k: v for k, v in os.environ.items() if k.startswith("SLURM_")},
    }


def measure(distance, rounds, p, shots, workers, seed):
    """One seeded batch, a warmed pool, and one timed dispatch.

    Data generation, model construction, file creation, process spawn and warmup
    are excluded from dispatch_s. Returning predictions/IPC IS included.
    """
    partitions = bounds(shots, workers)
    proc = psutil.Process()
    try:
        available = len(proc.cpu_affinity())
    except (AttributeError, NotImplementedError):
        available = os.cpu_count() or 1
    allocated = int(os.environ.get("SLURM_CPUS_PER_TASK", available))
    if workers > min(available, allocated):
        raise ValueError("workers exceed visible/allocated CPUs")

    start = time.perf_counter()
    circuit = circuit_for(distance, rounds, p)
    model = circuit.detector_error_model(decompose_errors=True)
    model_s = time.perf_counter() - start
    start = time.perf_counter()
    syn, actual = seeded_data(circuit, shots, seed)
    sample_s = time.perf_counter() - start
    digest = hashlib.sha256(syn.tobytes() + actual.tobytes()).hexdigest()
    context = mp.get_context("spawn")
    barrier = context.Barrier(workers)
    with tempfile.TemporaryDirectory(prefix="qec-", dir=os.environ.get("QEC_TMPDIR")) as tmp:
        path = str(Path(tmp) / "syndromes.npy")
        np.save(path, syn)
        start = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                 initializer=_init_worker,
                                 initargs=(str(model), path, barrier)) as pool:
            pids = list(pool.map(_decode_chunk, partitions, [True] * workers))
            setup_s = time.perf_counter() - start
            if len(set(pids)) != workers:
                raise RuntimeError("Not all workers participated in warmup")
            start = time.perf_counter_ns()
            chunks = list(pool.map(_decode_chunk, partitions))
            dispatch_s = (time.perf_counter_ns() - start) / 1e9
        predicted = np.concatenate([x[0] for x in chunks], axis=0)
    if predicted.shape != actual.shape:
        raise RuntimeError(f"Invalid predictions: {predicted.shape} != {actual.shape}")
    failures = int(np.count_nonzero(np.any(predicted != actual, axis=1)))
    kernel_max_s = max(x[1] for x in chunks)
    cpu_s = sum(x[2] for x in chunks)
    return {
        "distance": distance, "rounds": rounds, "p": p, "shots": shots,
        "workers": workers, "seed": seed, "input_sha256": digest,
        "prediction_sha256": hashlib.sha256(predicted.tobytes()).hexdigest(),
        "detectors": circuit.num_detectors, "observables": circuit.num_observables,
        "model_s": model_s, "sample_s": sample_s, "pool_setup_warmup_s": setup_s,
        "dispatch_s": dispatch_s, "worker_decode_max_s": kernel_max_s,
        "worker_decode_sum_s": sum(x[1] for x in chunks), "worker_cpu_sum_s": cpu_s,
        "throughput_shots_s": shots / dispatch_s,
        "amortized_us_shot": dispatch_s * 1e6 / shots,
        "decode_cpu_percent_one_core": 100 * cpu_s / dispatch_s,
        "worker_rss_sum_bytes": sum(x[3] for x in chunks),
        "failures": failures, "logical_error_rate": failures / shots,
        "worker_pids": [x[4] for x in chunks],
    }
