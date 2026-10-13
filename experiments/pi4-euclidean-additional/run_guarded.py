"""Pi-native command runner, only inside a verified memory-limited cgroup."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import signal

parser = argparse.ArgumentParser()
parser.add_argument("--no-summary", action="store_true", help="Build/tool invocations only; not proof success")
parser.add_argument("--timeout-s", type=int, default=180)
parser.add_argument("command", nargs=argparse.REMAINDER)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--memory-max-mib", type=int, default=256)
parser.add_argument("--memory-high-mib", type=int, default=192)
args = parser.parse_args()
if args.command and args.command[0] == "--": args.command = args.command[1:]
assert args.command
assert 0 < args.timeout_s <= 1800
os.umask(0o077)
args.out.mkdir(mode=0o700)  # Refuse overwrite/reuse of an incomplete run.
cg = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::", 1)[1].lstrip("/")
parent = Path("/sys/fs/cgroup/week24.slice")
assert parent in cg.parents, "Benchmark must be inside the bounded experiment slice"
parent_limits = {name: int((parent / name).read_text()) for name in
                 ["memory.high", "memory.max", "memory.swap.max"]}
assert parent_limits == {"memory.high": 1200 * 1024**2, "memory.max": 1536 * 1024**2,
                         "memory.swap.max": 0}
assert subprocess.run(["systemctl", "is-active", "--quiet", "week24-memory-watchdog.service"],
                      timeout=2).returncode == 0, "OS reserve watchdog is not active"
watchdog_group = subprocess.check_output(["systemctl", "show", "week24-memory-watchdog.service",
                                         "-p", "ControlGroup", "--value"], text=True, timeout=2).strip()
assert not watchdog_group.startswith("/week24.slice/"), "Watchdog must remain outside experiment slice"
ssh_pid = subprocess.check_output(["systemctl", "show", "ssh.service", "-p", "MainPID", "--value"],
                                  text=True, timeout=2).strip()
assert int(Path(f"/proc/{ssh_pid}/oom_score_adj").read_text()) == -900, "SSH OOM protection not configured"

def integer(name):
    return int((cg / name).read_text().strip())

def events():
    return {k: int(v) for k, v in (line.split() for line in (cg / "memory.events").read_text().splitlines())}

def temperature():
    return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000

def throttled():
    r = subprocess.run(["vcgencmd", "get_throttled"], text=True, capture_output=True, check=True, timeout=2)
    return int(r.stdout.strip().split("=", 1)[1], 16)

limits = {n: integer(n) for n in ["memory.max", "memory.high", "memory.swap.max"]}
assert 0 < args.memory_high_mib < args.memory_max_mib <= 1536
assert limits == {"memory.max": args.memory_max_mib * 1024**2,
                  "memory.high": args.memory_high_mib * 1024**2, "memory.swap.max": 0}, limits
assert os.uname().machine == "aarch64", "Must run natively on Pi ARM64"
before = events()
temp_before = temperature()
throttle_before = throttled()
assert throttle_before & 0xF == 0, "Current undervoltage/throttling; defer performance run"
start = time.monotonic()
peak_swap = 0
samples = 0
cpu = min(os.sched_getaffinity(0))
throttle_samples = [throttle_before]
next_thermal = start + 0.25
def system_memory():
    return {k: int(v.split()[0]) * 1024 for k, v in
            (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            if k in ["MemAvailable", "SwapTotal", "SwapFree"]}

assert system_memory()["MemAvailable"] >= 1024 * 1024**2, "Insufficient OS reserve"
with (args.out / "benchmark.jsonl").open("x") as out, (args.out / "stderr.log").open("x") as err, \
        (args.out / "memory.jsonl").open("x") as memory_log:
    p = subprocess.Popen(["taskset", "-c", str(cpu), *args.command],
                         env={**os.environ, "GOMAXPROCS": "1", "RAYON_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}, stdout=out, stderr=err, start_new_session=True)
    reason = None
    try:
        while p.poll() is None:
            samples += 1
            peak_swap = max(peak_swap, integer("memory.swap.current"))
            now = time.monotonic()
            smem = system_memory()
            proc_mem = {}
            try:
                for line in Path(f"/proc/{p.pid}/status").read_text().splitlines():
                    if line.startswith(("VmRSS:", "VmHWM:")):
                        k, v = line.split(":", 1)
                        proc_mem[k] = int(v.split()[0]) * 1024
                for line in Path(f"/proc/{p.pid}/smaps_rollup").read_text().splitlines():
                    if line.startswith("Pss:"):
                        proc_mem["Pss"] = int(line.split()[1]) * 1024
            except (FileNotFoundError, ProcessLookupError):
                pass  # Process may finish between poll and /proc read.
            memory_log.write(json.dumps({"elapsed_s": now - start,
                                        "cgroup_current_bytes": integer("memory.current"),
                                        "cgroup_swap_bytes": integer("memory.swap.current"),
                                        "system_available_bytes": smem["MemAvailable"],
                                        "system_swap_used_bytes": smem["SwapTotal"] - smem["SwapFree"],
                                        "process": proc_mem}) + "\n")
            if smem["MemAvailable"] < 1024 * 1024**2:
                reason = "os_memory_reserve"
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                break
            if now >= next_thermal:
                throttle_samples.append(throttled())
                next_thermal = now + 0.25
                if throttle_samples[-1] & 0xF:
                    reason = "current_undervoltage_or_throttling"
                    os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
                        p.wait()
                    break
            if time.monotonic() - start > args.timeout_s:
                reason = "timeout"
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                break
            time.sleep(0.01)
    except Exception as exc:
        reason = "telemetry_error:" + type(exc).__name__
        print(json.dumps({"phase": "monitor-error", "error_type": type(exc).__name__,
                          "stop_reason": reason}))
    finally:
        # Preserve fail-closed behavior and stop the complete process group,
        # even when vcgencmd or /proc sampling fails during a proof.
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()

after = events()
try:
    throttle_after = throttled()
except Exception as exc:
    throttle_after = None
    reason = reason or "final_telemetry_error:" + type(exc).__name__
if throttle_after is not None:
    throttle_samples.append(throttle_after)
peak = integer("memory.peak")
summary = {"phase": "resource", "exit_code": p.returncode, "parent_limits_bytes": parent_limits,
           "ssh_oom_score_adj": -900, "watchdog_verified_outside_slice": True,
           "elapsed_s": time.monotonic() - start, "limits_bytes": limits,
           "cgroup_peak_bytes": peak, "sampled_swap_peak_bytes": peak_swap,
           "poll_interval_ms": 10, "poll_samples": samples,
           "memory_events_before": before, "memory_events_after": after,
           "temperature_before_C": temp_before, "temperature_after_C": temperature(),
           "throttled_before": hex(throttle_before), "throttled_after": hex(throttle_after) if throttle_after is not None else None,
           "throttle_samples": [hex(x) for x in throttle_samples],
           "thermal_poll_interval_ms": 250, "benchmark_cpu_affinity": [cpu],
           "stop_reason": reason, "scope": "whole unit including runner and all child processes; sampled process RSS is command leader only"}
(args.out / "resource.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
assert p.returncode == 0 and reason is None, "Benchmark or telemetry failed; preserve logs"
assert after.get("oom_kill", 0) == before.get("oom_kill", 0)
assert throttle_after is not None and throttle_after & 0xF == 0, "Current throttling during/after trial; not a clean baseline"
assert all(x & 0xF == 0 for x in throttle_samples)
if not args.no_summary:
    rows = [json.loads(line) for line in (args.out / "benchmark.jsonl").read_text().splitlines() if line.strip().startswith("{")]
    assert rows and rows[-1]["phase"] == "summary" and rows[-1]["all_verified"], "No successful proof summary"
