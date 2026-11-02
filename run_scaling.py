"""Run a validated JSON experiment matrix; append each completed observation."""
import argparse
import datetime as dt
import hashlib
import itertools
import json
import random
import subprocess
import uuid
from pathlib import Path

from qec_bench import hardware, measure


def cases_from(config):
    if config.get("schema_version") != 1 or config["repetitions"] < 1:
        raise ValueError("Unsupported schema or invalid repetitions")
    cases = []
    for exp in config["experiments"]:
        for d, n, w in itertools.product(exp["distances"], exp["shots"], exp["workers"]):
            cases.append(dict(experiment=exp["name"], distance=d,
                              rounds=exp.get("rounds", d), p=exp["p"], shots=n, workers=w))
    return cases


def run(config_path, output="results", workers=None, label="local"):
    raw = Path(config_path).read_bytes()
    config = json.loads(raw)
    cases = cases_from(config)
    if workers is not None:
        cases = [c for c in cases if c["workers"] == workers]
    if not cases:
        raise ValueError("No selected cases")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = Path(output) / run_id
    destination.mkdir(parents=True)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
                                           text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    metadata = dict(run_id=run_id, label=label, config=config,
                    config_sha256=hashlib.sha256(raw).hexdigest(), git_revision=revision,
                    git_dirty=dirty, hardware=hardware(),
                    source_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in Path(__file__).parent.glob("*.py")})
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    rng = random.Random(config["seed"])
    # Repetitions are fresh datasets/pools; all worker counts get the same seed.
    with (destination / "measurements.jsonl").open("w", encoding="utf-8") as file:
        for repeat in range(config["repetitions"]):
            ordered = cases.copy()
            rng.shuffle(ordered)
            for case in ordered:
                experiment = case["experiment"]
                params = {k: v for k, v in case.items() if k != "experiment"}
                row = measure(**params, seed=config["seed"] + repeat)
                row.update(run_id=run_id, experiment=experiment, repetition=repeat,
                           timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                file.write(json.dumps(row) + "\n")
                file.flush()
                print(f"{experiment} rep={repeat} d={row['distance']} n={row['shots']} "
                      f"w={row['workers']} {row['throughput_shots_s']:,.0f} shots/s", flush=True)
    print(f"Results: {destination}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/local.json")
    parser.add_argument("--output", default="results")
    parser.add_argument("--workers", type=int, help="Filter matrix for allocated worker count")
    parser.add_argument("--label", default="local")
    args = parser.parse_args()
    run(args.config, args.output, args.workers, args.label)
