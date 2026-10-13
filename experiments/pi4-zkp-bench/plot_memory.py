"""Render short startup profiles; these plots do not establish steady-state/leak behavior."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[2]
runs = sorted((root / "week24/logs/pi-gnark-tiny").iterdir())
assert len(runs) == 4, "Initial four-run figure; adapt layout explicitly for additional runs"
fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey=True)
for ax, folder in zip(axes.flat, runs):
    rows = [json.loads(line) for line in (folder / "memory.jsonl").read_text().splitlines()]
    resource = json.loads((folder / "resource.json").read_text())
    ax.plot([r["elapsed_s"] for r in rows], [r["cgroup_current_bytes"] / 2**20 for r in rows],
            label="Unit cgroup current", color="#1565c0", linewidth=2)
    rss = [r for r in rows if "VmRSS" in r["process"]]
    ax.plot([r["elapsed_s"] for r in rss], [r["process"]["VmRSS"] / 2**20 for r in rss],
            label="Go process RSS", color="#ef6c00", linewidth=1.5)
    ax.axhline(resource["cgroup_peak_bytes"] / 2**20, label="Kernel cgroup peak", color="#ad1457", linestyle=":")
    ax.set_title(folder.name, fontsize=10)
    ax.set_xlabel("Elapsed time from child launch (s)")
    ax.set_ylabel("Memory (MiB)")
    ax.set_ylim(0, 25)
    ax.grid(alpha=.25)
    ax.legend(loc="lower right", fontsize=8)
fig.suptitle("Pi4: gnark Groth16 toy (12 constraints), short startup memory profiles", fontsize=12)
fig.text(.5, .025, "10 ms sampling; each run = 1 warmup + 20 proofs. Cache not cleared. Not a leak test.", ha="center", fontsize=9)
fig.tight_layout(rect=(0, .05, 1, .95))
out = root / "week24/plots"
out.mkdir(exist_ok=True)
fig.savefig(out / "pi-gnark-tiny-memory.png", dpi=160)
fig.savefig(out / "pi-gnark-tiny-memory.svg")
svg = out / "pi-gnark-tiny-memory.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
print("Saved startup memory profiles")
