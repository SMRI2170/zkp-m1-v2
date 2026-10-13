"""Install runtime-only experiment limits/SSH protection; no SSH restart."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert "memory" in Path("/sys/fs/cgroup/cgroup.controllers").read_text().split()
parser = argparse.ArgumentParser()
parser.add_argument("--watchdog-sha256", required=True)
parser.add_argument("--harden-existing", action="store_true")
args = parser.parse_args()
watchdog_bytes = Path(__file__).with_name("memory_watchdog.py").read_bytes()
assert hashlib.sha256(watchdog_bytes).hexdigest() == args.watchdog_sha256
protected_dir = Path("/run/week24")
protected_dir.mkdir(mode=0o755, exist_ok=True)
assert protected_dir.stat().st_uid == 0 and protected_dir.stat().st_mode & 0o022 == 0
protected_script = protected_dir / "memory_watchdog.py"
with protected_script.open("xb") as f:
    f.write(watchdog_bytes)
protected_script.chmod(0o644)
root = Path("/run/systemd/system")
slice_file = root / "week24.slice"
watchdog = root / "week24-memory-watchdog.service"
if args.harden_existing:
    original = watchdog.read_text()
    old = "ExecStart=/usr/bin/python3 /home/pi/.cache/week24/memory_watchdog.py"
    assert original.count(old) == 1
    backup = protected_dir / "watchdog-unit-before-hardening.txt"
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(original)
    watchdog.write_text(original.replace(old, "ExecStart=/usr/bin/python3 /run/week24/memory_watchdog.py"))
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "week24-memory-watchdog.service"], check=True)
    print(json.dumps({"watchdog_root_owned": protected_script.stat().st_uid == 0,
                      "watchdog_not_group_or_other_writable": protected_script.stat().st_mode & 0o022 == 0,
                      "watchdog_sha256": args.watchdog_sha256, "ssh_restarted": False}))
    raise SystemExit(0)
assert not slice_file.exists(), "Existing experiment slice; inspect before changing"
slice_file.write_text("""[Unit]
Description=Week24 bounded ZKP experiments
[Slice]
MemoryAccounting=yes
MemoryHigh=1200M
MemoryMax=1536M
MemorySwapMax=0
""")
drop = root / "ssh.service.d/week24-memory-guard.conf"
drop.parent.mkdir(exist_ok=True)
assert not drop.exists()
drop.write_text("[Service]\nOOMScoreAdjust=-900\n")
assert not watchdog.exists()
watchdog.write_text("""[Unit]
Description=Week24 OS memory reserve watchdog
[Service]
ExecStart=/usr/bin/python3 /run/week24/memory_watchdog.py
MemoryAccounting=yes
MemoryHigh=48M
MemoryMax=64M
MemorySwapMax=0
OOMScoreAdjust=-500
Restart=on-failure
""")
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(["systemctl", "start", "week24.slice", "week24-memory-watchdog.service"], check=True)
protected = 0
for proc in Path("/proc").iterdir():
    if proc.name.isdecimal():
        try:
            if (proc / "comm").read_text().strip() == "sshd":
                (proc / "oom_score_adj").write_text("-900\n")
                protected += 1
        except FileNotFoundError:
            pass
cg = Path("/sys/fs/cgroup/week24.slice")
limits = {name: int((cg / name).read_text()) for name in
          ["memory.high", "memory.max", "memory.swap.max"]}
assert limits == {"memory.high": 1200 * 1024**2, "memory.max": 1536 * 1024**2, "memory.swap.max": 0}
assert subprocess.run(["systemctl", "is-active", "week24-memory-watchdog.service"],
                      capture_output=True).returncode == 0
print(json.dumps({"experiment_slice_limits": limits, "sshd_processes_protected": protected,
                  "sshd_oom_score_adj": -900, "os_reserve_bytes": 1024 * 1024**2,
                  "watchdog_outside_experiment_slice": True, "ssh_restarted": False,
                  "guard_config_runtime_only": True}))
