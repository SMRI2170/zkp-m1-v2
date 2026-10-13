"""Root-only, backed-up one-line boot change; does not reboot by itself."""
import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--expected-sha256", required=True)
parser.add_argument("--backup", type=Path, required=True)
args = parser.parse_args()
assert os.geteuid() == 0
path = Path("/boot/firmware/cmdline.txt")
original = path.read_bytes()
assert hashlib.sha256(original).hexdigest() == args.expected_sha256, "Boot config changed; inspect again"
line = original.decode().strip()
assert "\n" not in line and "cgroup_enable=memory" not in line.split()
args.backup.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
assert args.backup.parent.stat().st_mode & 0o777 == 0o700
fd = os.open(args.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as f:
    f.write(original)
    f.flush()
    os.fsync(f.fileno())
modified = (line + " cgroup_enable=memory\n").encode()
with path.open("wb") as f:
    f.write(modified)
    f.flush()
    os.fsync(f.fileno())
assert path.read_bytes() == modified
print(json.dumps({"backup_preserved": True, "before_sha256": args.expected_sha256,
                  "after_sha256": hashlib.sha256(modified).hexdigest(),
                  "added_parameter": "cgroup_enable=memory", "reboot_required": True}))
