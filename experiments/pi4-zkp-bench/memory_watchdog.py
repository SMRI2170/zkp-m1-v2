"""Outside the experiment slice: stop only experiment work if OS headroom falls."""
import json
from pathlib import Path
import subprocess
import time

reserve = 1024 * 1024**2
while True:
    mem = {k: int(v.split()[0]) * 1024 for k, v in
           (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
           if k == "MemAvailable"}
    if mem["MemAvailable"] < reserve:
        print(json.dumps({"action": "stop_experiment_slice", "mem_available_bytes": mem["MemAvailable"],
                          "reserve_bytes": reserve}), flush=True)
        subprocess.run(["systemctl", "stop", "week24.slice"], check=True, timeout=10)
        time.sleep(1)
    time.sleep(0.1)
