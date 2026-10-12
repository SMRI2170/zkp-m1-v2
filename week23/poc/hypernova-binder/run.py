"""Run local-only synthetic binder experiments; preserve every attempt log."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

root = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["plan", "check", "prove"])
args = parser.parse_args()
log = root / f"week23/logs/hypernova-binder-{args.mode}.log"
attempt = 1
while log.exists():
    log = root / f"week23/logs/hypernova-binder-{args.mode}-attempt-{attempt}.log"
    attempt += 1
start = time.monotonic()
peak = 0
reason = None
with log.open("x") as output:
    process = subprocess.Popen(
        [str(root / ".cache/week23/target-hypernova-binder/release/week23-hypernova-binder"), args.mode],
        cwd=root, stdout=output, stderr=subprocess.STDOUT,
        env={**os.environ, "RAYON_NUM_THREADS": "2"},
    )
    while process.poll() is None:
        raw = subprocess.check_output(["ps", "-o", "rss=", "-p", str(process.pid)], text=True).strip()
        rss = int(raw or "0") * 1024
        peak = max(peak, rss)
        swap = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
        used = float(re.search(r"used = ([\d.]+)M", swap)[1])
        if rss > 4.5 * 1024**3 or used > 7500:
            reason = {"reason": "resource_ceiling", "rss_bytes": rss, "swap_used_MiB": used}
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            break
        time.sleep(1)
summary = {"mode": args.mode, "exit_code": process.returncode,
           "peak_rss_bytes": peak, "elapsed_s": time.monotonic() - start,
           "ceiling": reason, "rss_ceiling_GiB": 4.5, "swap_ceiling_MiB": 7500}
log.with_name(log.stem + "-resource.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
raise SystemExit(0 if process.returncode == 0 else 1)
