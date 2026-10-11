"""Prepare the pinned research source and locked dependencies; never handles proof caches."""
from pathlib import Path
import subprocess, shutil
root = Path(__file__).resolve().parents[3]
dest = root / '.cache/week23/sources/arecibo'
revision = '8997d733aa69c3b6db5a44e06f7c0f74ad315d6f'
if not dest.exists():
    subprocess.run(['git', 'clone', '--no-checkout', 'https://github.com/lurk-lang/arecibo', str(dest)], check=True)
    subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', revision], check=True)
head = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
if head != revision:
    raise SystemExit('Existing source revision differs; preserved for inspection: ' + head)
patch = root / 'week23/manifests/arecibo-build.patch'
cmd = ['git', '-C', str(dest), 'apply']
if subprocess.run(cmd + ['--reverse', '--check', str(patch)], capture_output=True).returncode != 0:
    subprocess.run(cmd + ['--check', str(patch)], check=True)
    subprocess.run(cmd + [str(patch)], check=True)
lock = root / 'week23/manifests/arecibo.Cargo.lock'
if (dest / 'Cargo.lock').exists() and (dest / 'Cargo.lock').read_bytes() != lock.read_bytes():
    raise SystemExit('Existing lock differs; preserved for inspection')
shutil.copyfile(lock, dest / 'Cargo.lock')
print('Prepared pinned Arecibo; run the README test command with --locked')
