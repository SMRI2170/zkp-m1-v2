"""Describe sampled memory distributions/trends; never infer leaks from short runs."""
import argparse
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
args = parser.parse_args()
rows = [json.loads(line) for line in (args.run / "memory.jsonl").read_text().splitlines()]
assert len(rows) >= 2, "Insufficient memory samples"
resource = json.loads((args.run / "resource.json").read_text())

def quantile(xs, p):
    a = sorted(xs)
    f = (len(a) - 1) * p
    i = int(f)
    return a[i] if i + 1 == len(a) else a[i] + (a[i + 1] - a[i]) * (f - i)

def describe(xs):
    return {"n": len(xs), "min_bytes": min(xs), "max_bytes": max(xs),
            "mean_bytes": statistics.mean(xs), "stddev_bytes": statistics.pstdev(xs),
            "p50_bytes": quantile(xs, .5), "p95_bytes": quantile(xs, .95), "p99_bytes": quantile(xs, .99)}

t = [r["elapsed_s"] for r in rows]
x = [r["cgroup_current_bytes"] for r in rows]
tm, xm = statistics.mean(t), statistics.mean(x)
denom = sum((v - tm)**2 for v in t)
slope = sum((a - tm) * (b - xm) for a, b in zip(t, x)) / denom
durations = [b - a for a, b in zip(t, t[1:])]
weighted_mean = sum(a * d for a, d in zip(x, durations)) / sum(durations)
weighted = sorted(zip(x[:-1], durations))

def weighted_quantile(p):
    total = sum(durations)
    acc = 0
    for value, duration in weighted:
        acc += duration
        if acc >= p * total:
            return value
    return weighted[-1][0]

result = {"samples": len(rows), "observed_span_s": t[-1] - t[0],
          "quantile_definition": "sample quantiles: linear interpolation; time-weighted: previous sample held until next",
          "whole_unit_sampled": describe(x),
          "time_weighted": {"mean_bytes": weighted_mean, "p50_bytes": weighted_quantile(.5),
                            "p95_bytes": weighted_quantile(.95), "p99_bytes": weighted_quantile(.99)},
          "cgroup_kernel_peak_bytes": resource["cgroup_peak_bytes"],
          "system_available": describe([r["system_available_bytes"] for r in rows]),
          "system_swap_used_max_bytes": max(r["system_swap_used_bytes"] for r in rows),
          "cgroup_swap_max_bytes": max(r["cgroup_swap_bytes"] for r in rows),
          "ols_whole_run_slope_bytes_per_s": slope,
          "first_to_last_bytes": x[-1] - x[0],
          "limitation": "Short startup-inclusive, autocorrelated observations; slope is not evidence of a leak and is not a steady-state estimate"}
for key in ["VmRSS", "VmHWM", "Pss"]:
    values = [r["process"][key] for r in rows if key in r["process"]]
    if values:
        result["process_" + key] = describe(values)
(args.run / "memory-summary.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
