"""Aggregate comparable runs; validate paired inputs before computing speedups."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

KEYS = ("cohort", "experiment", "distance", "rounds", "p", "shots", "workers")
METRICS = ("dispatch_s", "throughput_shots_s", "amortized_us_shot", "worker_decode_max_s",
           "pool_setup_warmup_s", "worker_rss_sum_bytes")


def quartiles(values):
    q1, med, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    return float(med), float(q1), float(q3)


def load(paths):
    rows, metadata = [], {}
    for root in paths:
        for file in sorted(Path(root).rglob("measurements.jsonl")):
            meta = json.loads(file.with_name("metadata.json").read_text(encoding="utf-8"))
            hw = meta["hardware"]
            identity = {k: hw[k] for k in ("hostname", "processor", "platform", "versions")}
            identity.update(label=meta["label"], config_sha256=meta["config_sha256"],
                            source_hashes=meta["source_hashes"])
            cohort = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
            metadata[cohort] = identity
            for line in file.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                row["cohort"] = cohort
                rows.append(row)
    if not rows:
        raise ValueError("No measurements found")
    seen = set()
    for row in rows:
        key = tuple(row[k] for k in KEYS) + (row["repetition"], row["seed"])
        if key in seen:
            raise ValueError("Duplicate case/repetition: analyse reruns separately")
        seen.add(key)
    return rows, metadata


def summarise(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in KEYS)].append(row)
    result = []
    for key, values in sorted(groups.items()):
        row = dict(zip(KEYS, key))
        row["repetitions"] = len(values)
        for metric in METRICS:
            med, q1, q3 = quartiles([r[metric] for r in values])
            row.update({metric + "_median": med, metric + "_q1": q1, metric + "_q3": q3})
        # Unique seeded shot sets; repetitions are not redecodes of one dataset.
        shots = sum(r["shots"] for r in values)
        failures = sum(r["failures"] for r in values)
        proportion = failures / shots
        z = 1.96
        denom = 1 + z*z / shots
        centre = (proportion + z*z/(2*shots)) / denom
        half = z * np.sqrt(proportion*(1-proportion)/shots + z*z/(4*shots*shots)) / denom
        row.update(failures=failures, total_shots=shots, logical_error_rate=proportion,
                   ler_wilson_low=max(0, centre-half), ler_wilson_high=min(1, centre+half))
        result.append(row)
    return result


def paired_speedups(rows):
    groups = defaultdict(dict)
    for row in rows:
        if row["experiment"] != "strong_scaling":
            continue
        key = tuple(row[k] for k in ("cohort", "distance", "rounds", "p", "shots", "repetition", "seed"))
        groups[key][row["workers"]] = row
    result = []
    for key, by_workers in sorted(groups.items()):
        if 1 not in by_workers:
            raise ValueError("Strong scaling needs a matching 1-worker baseline")
        base = by_workers[1]
        for workers, row in sorted(by_workers.items()):
            for field in ("input_sha256", "prediction_sha256", "failures"):
                if row[field] != base[field]:
                    raise ValueError(f"Parallel correctness/comparability failure: {field}")
            speedup = base["dispatch_s"] / row["dispatch_s"]
            result.append(dict(cohort=key[0], distance=key[1], rounds=key[2], p=key[3],
                               shots=key[4], repetition=key[5], seed=key[6],
                               workers=workers, speedup=speedup, efficiency=speedup/workers))
    return result


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_summaries(summary, speedups, output):
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "font.size": 10, "figure.dpi": 150})
    for cohort in sorted({r["cohort"] for r in summary}):
        data = [r for r in summary if r["cohort"] == cohort]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
        for ax, exp, xkey, ylabel in [
            (axes[0], "batch_size", "shots", "Dispatch throughput (shots/s)"),
            (axes[1], "complexity", "distance", "Amortized dispatch cost (µs/shot)")]:
            series = sorted([r for r in data if r["experiment"] == exp], key=lambda r:r[xkey])
            metric = "throughput_shots_s" if exp == "batch_size" else "amortized_us_shot"
            if series:
                med = np.array([r[metric+"_median"] for r in series])
                low = med - [r[metric+"_q1"] for r in series]
                high = [r[metric+"_q3"] for r in series] - med
                ax.errorbar([r[xkey] for r in series], med, yerr=[low,high],
                            marker="o", capsize=4, color="#226C9E")
            ax.set(xlabel="Shots per batch" if xkey=="shots" else "Code distance (rounds = distance)",
                   ylabel=ylabel, title="Batch amortisation" if xkey=="shots" else "Space-time complexity")
            if xkey=="shots":
                ax.set_xscale("log")
            ax.grid(alpha=0.2)
        fig.suptitle("Offline PyMatching · median and IQR across repetitions")
        fig.savefig(output / f"workload-{cohort}.png")
        plt.close(fig)

        values = [r for r in speedups if r["cohort"] == cohort]
        if values:
            fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
            controls = {(r["distance"], r["rounds"], r["p"]) for r in values}
            for shots, distance, rounds, p in sorted({(r["shots"], r["distance"], r["rounds"], r["p"]) for r in values}):
                selected = [r for r in values if (r["shots"], r["distance"], r["rounds"], r["p"]) == (shots, distance, rounds, p)]
                label = f"{shots:,} shots"
                if len(controls) > 1:
                    label += f", d={distance}, r={rounds}, p={p}"
                ws = sorted({r["workers"] for r in selected})
                for ax, metric in zip(axes, ("speedup", "efficiency")):
                    qs = np.array([quartiles([r[metric] for r in selected if r["workers"]==w]) for w in ws])
                    ax.errorbar(ws, qs[:,0], yerr=[qs[:,0]-qs[:,1], qs[:,2]-qs[:,0]],
                                marker="o", capsize=4, label=label)
            maximum = max(r["workers"] for r in values)
            axes[0].plot([1, maximum], [1, maximum], "--", color="gray", label="Ideal")
            axes[1].axhline(1, linestyle="--", color="gray")
            for ax, title, ylabel in zip(axes, ("Strong scaling", "Resource efficiency"),
                                         ("Paired speedup vs 1 worker", "Speedup / worker count")):
                ax.set(xlabel="Independent worker processes", ylabel=ylabel, title=title)
                ax.set_xticks(ws)
                ax.legend()
                ax.grid(alpha=0.2)
            fig.suptitle("Fixed total workload · paired median and IQR")
            fig.savefig(output / f"scaling-{cohort}.png")
            plt.close(fig)


def analyse(paths, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows, metadata = load(paths)
    summary = summarise(rows)
    paired = paired_speedups(rows)
    write_csv(output / "raw.csv", rows)
    write_csv(output / "summary.csv", summary)
    write_csv(output / "paired_speedups.csv", paired)
    (output / "cohorts.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    plot_summaries(summary, paired, output)
    print(f"Analysed {len(rows)} measurements, {len(summary)} cases, {len(metadata)} cohort(s)")
    for row in summary:
        print(f"{row['experiment']:15} d={row['distance']} n={row['shots']:6} w={row['workers']} "
              f"{row['throughput_shots_s_median']:10,.0f} shots/s "
              f"[{row['throughput_shots_s_q1']:,.0f}, {row['throughput_shots_s_q3']:,.0f}] IQR")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Result directory/directories")
    parser.add_argument("--output", default="figures")
    args = parser.parse_args()
    analyse(args.paths, args.output)
