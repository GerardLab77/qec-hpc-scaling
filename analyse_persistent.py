"""Validate a complete persistent-pool campaign and report paired speedups."""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from persistent_pool import cases_from

CASE = ("experiment", "distance", "rounds", "p", "shots", "workers", "batches")
METRICS = ("pool_setup_warmup_s", "pool_shutdown_s", "dispatch_sum_s",
           "decode_service_s", "workload_wall_s", "warmed_throughput_shots_s",
           "service_throughput_shots_s", "workload_throughput_shots_s")
TIMINGS = {"warmed": "dispatch_sum_s", "service": "decode_service_s",
           "workload": "workload_wall_s"}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate(root):
    root = Path(root)
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if meta.get("schema") != "qec-persistent-v1" or not (root / "COMPLETE").is_file():
        raise ValueError("Not a complete persistent campaign; retain partial files for diagnosis")
    config = meta["config"]
    cases = cases_from(config)
    expected = {tuple(c[k] for k in CASE) + (repeat,)
                for c in cases for repeat in range(config["repetitions"])}
    summaries = read_jsonl(root / "persistent_measurements.jsonl")
    batches = read_jsonl(root / "persistent_batches.jsonl")
    by_session = defaultdict(list)
    for row in batches:
        by_session[row["session_id"]].append(row)
    seen, sessions = set(), set()
    stride = max(c["batches"] for c in cases)
    for row in summaries:
        key = tuple(row[k] for k in CASE) + (row["repetition"],)
        session = row["session_id"]
        if key in seen or session in sessions:
            raise ValueError("Duplicate case/repetition or session")
        seen.add(key)
        sessions.add(session)
        if row["run_id"] != meta["run_id"]:
            raise ValueError("Run identity mismatch")
        seed = config["seed"] + row["repetition"] * stride
        if row["seed"] != seed or row["total_shots"] != row["shots"] * row["batches"]:
            raise ValueError("Seed or shot count mismatch")
        values = sorted(by_session[session], key=lambda b: b["batch_index"])
        if [b["batch_index"] for b in values] != list(range(row["batches"])):
            raise ValueError("Missing or duplicate batches")
        pids = None
        for index, batch in enumerate(values):
            if any(batch[k] != row[k] for k in CASE + ("repetition", "run_id")):
                raise ValueError("Batch/session controls mismatch")
            if batch["batch_seed"] != seed + index:
                raise ValueError("Batch seed mismatch")
            if not 0 <= batch["failures"] <= row["shots"]:
                raise ValueError("Invalid failure count")
            for field in ("input_sha256", "prediction_sha256"):
                digest = batch[field]
                if (not isinstance(digest, str) or len(digest) != 64 or
                        any(c not in "0123456789abcdef" for c in digest)):
                    raise ValueError("Invalid batch hash")
            workers = set(batch["worker_pids"])
            if len(workers) != row["workers"] or len(batch["worker_pids"]) != row["workers"]:
                raise ValueError("Missing workers")
            if pids is not None and workers != pids:
                raise ValueError("Worker pool changed between batches")
            pids = workers
            if not math.isfinite(batch["dispatch_s"]) or batch["dispatch_s"] <= 0:
                raise ValueError("Invalid batch timing")
        for metric in METRICS:
            if not math.isfinite(row[metric]) or row[metric] <= 0:
                raise ValueError(f"Invalid metric: {metric}")
        dispatch = sum(b["dispatch_s"] for b in values)
        service = row["pool_setup_warmup_s"] + dispatch + row["pool_shutdown_s"]
        if not math.isclose(dispatch, row["dispatch_sum_s"], rel_tol=1e-9):
            raise ValueError("Dispatch total mismatch")
        if not math.isclose(service, row["decode_service_s"], rel_tol=1e-9):
            raise ValueError("Service total mismatch")
        if row["workload_wall_s"] < service:
            raise ValueError("Workload wall time excludes lifecycle stages")
        for name, timer in TIMINGS.items():
            throughput = row[f"{name}_throughput_shots_s"]
            if not math.isclose(throughput, row["total_shots"] / row[timer], rel_tol=1e-9):
                raise ValueError("Throughput inconsistent with timing")
    if seen != expected or sessions != set(by_session):
        raise ValueError("Campaign has missing, unexpected or orphan observations")
    return summaries, by_session


def paired_speedups(rows, by_session):
    groups = defaultdict(dict)
    for row in rows:
        key = tuple(row[k] for k in CASE if k != "workers") + (row["repetition"], row["seed"])
        if row["workers"] in groups[key]:
            raise ValueError("Duplicate paired worker count")
        groups[key][row["workers"]] = row
    result = []
    for key, group in sorted(groups.items()):
        if 1 not in group:
            raise ValueError("Missing 1-worker baseline")
        base = group[1]

        def signature(row):
            return [(b["batch_index"], b["batch_seed"], b["input_sha256"],
                     b["prediction_sha256"], b["failures"])
                    for b in sorted(by_session[row["session_id"]], key=lambda b: b["batch_index"])]

        reference = signature(base)
        for workers, row in sorted(group.items()):
            if signature(row) != reference:
                raise ValueError("Paired input/prediction/failure mismatch")
            record = {k: row[k] for k in CASE + ("repetition", "seed")}
            for name, metric in TIMINGS.items():
                speedup = base[metric] / row[metric]
                record[name + "_speedup"] = speedup
                record[name + "_efficiency"] = speedup / workers
            result.append(record)
    return result


def aggregate(rows, metrics):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in CASE)].append(row)
    result = []
    for key, values in sorted(groups.items()):
        row = dict(zip(CASE, key), repetitions=len(values))
        for metric in metrics:
            q1, med, q3 = np.quantile([r[metric] for r in values], [.25, .5, .75])
            row.update({metric + "_median": float(med), metric + "_q1": float(q1),
                        metric + "_q3": float(q3)})
        result.append(row)
    return result


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyse(root, output):
    # Validate everything before creating reports. Never summarise a partial run.
    rows, batches = validate(root)
    paired = paired_speedups(rows, batches)
    summary = aggregate(rows, METRICS)
    speedups = aggregate(paired, tuple(name + suffix for name in TIMINGS
                                       for suffix in ("_speedup", "_efficiency")))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "sessions.csv", rows)
    write_csv(output / "summary.csv", summary)
    write_csv(output / "paired_speedups.csv", paired)
    write_csv(output / "speedup_summary.csv", speedups)
    controls = sorted({(r["experiment"], r["distance"], r["rounds"], r["p"], r["shots"])
                       for r in speedups})
    for index, control in enumerate(controls):
        data = [r for r in speedups if
                (r["experiment"], r["distance"], r["rounds"], r["p"], r["shots"]) == control]
        fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
        for ax, name in zip(axes, TIMINGS):
            for workers in sorted({r["workers"] for r in data}):
                series = sorted((r for r in data if r["workers"] == workers), key=lambda r: r["batches"])
                metric = name + "_speedup"
                med = np.array([r[metric + "_median"] for r in series])
                low = med - [r[metric + "_q1"] for r in series]
                high = [r[metric + "_q3"] for r in series] - med
                ax.errorbar([r["batches"] for r in series], med, yerr=[low, high],
                            marker="o", capsize=3, label=f"{workers} workers")
            ax.axhline(1, color="gray", linestyle="--")
            ax.set(xscale="log", xlabel="Batches per pool", ylabel="Paired speedup vs 1 worker",
                   title={"warmed": "Dispatch only", "service": "Setup + dispatches + shutdown",
                          "workload": "Full measured workload"}[name])
            ax.grid(alpha=.2)
        axes[-1].legend()
        fig.suptitle(f"{control[0]} · d={control[1]}, rounds={control[2]}, p={control[3]} · "
                     f"{control[4]:,} shots/batch · median and IQR")
        fig.savefig(output / f"persistent-{index}.png", dpi=150)
        plt.close(fig)
    print(f"Validated {len(rows)} sessions and {sum(len(v) for v in batches.values())} batches")
    for row in speedups:
        print(f"shots={row['shots']} batches={row['batches']:3} w={row['workers']:2} "
              f"paired speedup: warmed={row['warmed_speedup_median']:.3f}x "
              f"service={row['service_speedup_median']:.3f}x "
              f"workload={row['workload_speedup_median']:.3f}x")
    return summary, speedups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="One complete persistent run directory")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    analyse(args.run, args.output)
