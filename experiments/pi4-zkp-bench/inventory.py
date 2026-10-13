"""Public-safe Pi inventory: omit IP/MAC, passwords, serial, boot ID, and keys."""
import json
from pathlib import Path
import os
import subprocess
import time

def command(args):
    p = subprocess.run(args, capture_output=True, text=True)
    return {"exit_code": p.returncode, "stdout": p.stdout.strip()}

mem = {k: int(v.split()[0]) * 1024 for k, v in
       (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
       if k in ["MemTotal", "MemAvailable", "SwapTotal", "SwapFree"]}
stat = os.statvfs(str(Path.home()))
output = {"date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "machine": os.uname().machine, "kernel": os.uname().release,
          "model": Path("/proc/device-tree/model").read_text().rstrip("\0"),
          "os": {k: v.strip('"') for k, v in
                 (line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines())
                 if k in ["PRETTY_NAME", "ID", "VERSION_ID"]},
          "memory_bytes": mem, "available_cpus": sorted(os.sched_getaffinity(0)),
          "uptime_s": float(Path("/proc/uptime").read_text().split()[0]),
          "temperature_C": int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000,
          "throttled": command(["vcgencmd", "get_throttled"]),
          "cgroup_controllers": Path("/sys/fs/cgroup/cgroup.controllers").read_text().strip().split(),
          "memory_cgroup_enabled": next(line.split()[-1] == "1" for line in
                                        Path("/proc/cgroups").read_text().splitlines()
                                        if line.startswith("memory\t")),
          "filesystem_available_bytes": stat.f_bavail * stat.f_frsize,
          "python": command(["python3", "--version"]),
          "systemd": command(["systemctl", "--version"]),
          "time_sync": command(["timedatectl", "show", "-p", "NTPSynchronized"])}
print(json.dumps(output, indent=2))
