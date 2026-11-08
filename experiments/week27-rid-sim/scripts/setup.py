"""Bounded local setup, with per-command logs and no implicit global installs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def memory_evidence():
    if platform.system() == 'Darwin':
        total = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
        pressure = subprocess.check_output(['memory_pressure'], text=True)
        match = re.search(r'System-wide memory free percentage: (\d+)%', pressure)
        return dict(total_bytes=total, free_percentage=int(match[1]) if match else None,
                    swap_usage=subprocess.check_output(['sysctl', '-n', 'vm.swapusage'], text=True).strip())
    if platform.system() == 'Linux':
        values = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            if key in ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree']:
                values[key] = int(value.split()[0]) * 1024
        return values
    return dict(unsupported_platform=True)


def command(argv, cwd, log):
    with log.open('w') as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    return dict(argv=[str(x) for x in argv], exit_code=result.returncode,
                log=log.name, sha256=hashlib.sha256(log.read_bytes()).hexdigest())


def fetch(workspace, lock):
    for item in lock['archives']:
        archive = workspace / item['file']
        if not archive.exists():
            temporary = archive.with_suffix('.partial')
            if temporary.exists():
                raise ValueError('Inspect preserved partial download before retrying: ' + str(temporary))
            with urllib.request.urlopen(item['url'], timeout=60) as response, temporary.open('xb') as stream:
                total = 0
                while data := response.read(1024 * 1024):
                    total += len(data)
                    if total > 128 * 1024 * 1024:
                        raise ValueError('Archive exceeds download budget')
                    stream.write(data)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('Download hash mismatch; preserving partial file')
            temporary.rename(archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Archive hash mismatch: ' + str(archive))
        if not (workspace / item['directory']).exists():
            with tarfile.open(archive) as stream:
                if sum(m.size for m in stream.getmembers()) > 1024**3:
                    raise ValueError('Unexpected extracted size')
                stream.extractall(workspace, filter='data')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, default=REPO / '.cache/issue70')
    p.add_argument('--stage', choices=['preflight', 'fetch', 'build'], default='preflight')
    p.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error('Use a new evidence directory')
    args.out.mkdir(parents=True)
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((REPO / '.cache').resolve()):
        p.error('Keep local dependencies in this repository ignored .cache/')
    workspace.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'upstream.lock.json').read_text())
    report = dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  platform=platform.platform(), machine=platform.machine(), stage=args.stage,
                  disk_free_bytes=shutil.disk_usage(workspace).free, commands=[],
                  status='HOST_PREFLIGHT_ONLY', simulation='NOT_RUN', jobs=args.jobs,
                  tools={x: shutil.which(x) for x in ['clang++', 'pkg-config', 'bison', 'flex', 'make', 'gmake', 'python3.12']})
    try:
        report['memory'] = memory_evidence()
        if args.stage == 'preflight':
            return
        if report['disk_free_bytes'] < 8 * 1024**3:
            raise ValueError('Need at least 8 GiB free before setup; no cleanup performed')
        fetch(workspace, lock)
        upstream = workspace / 'uli-net-sim'
        if not upstream.exists():
            result = command(['git', 'clone', '--no-checkout', lock['uli_net_sim']['url'], str(upstream)],
                             workspace, args.out / 'clone.log')
            report['commands'].append(result)
            if result['exit_code']:
                raise ValueError('Upstream clone failed')
            subprocess.run(['git', '-C', str(upstream), 'checkout', '--detach', lock['uli_net_sim']['sha']], check=True)
        sha = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        if sha != lock['uli_net_sim']['sha'] or subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain'], text=True).strip():
            raise ValueError('Upstream SHA mismatch or local edits; preserving checkout')
        report['upstream_sha'] = sha
        report['status'] = 'SOURCES_VERIFIED_NOT_BUILT'
        if args.stage == 'fetch':
            return
        mem = report['memory']
        available = mem.get('MemAvailable')
        if available is None and mem.get('free_percentage') is not None:
            available = mem['total_bytes'] * mem['free_percentage'] / 100
        if available is None or available < 3 * 1024**3:
            raise ValueError('Cannot confirm 3 GiB available memory; inspect memory/swap before building')
        python = shutil.which('python3.12')
        if not python:
            raise ValueError('Install Python 3.12 first; upstream embeds this ABI')
        if not (workspace / 'python/bin/python').exists():
            subprocess.run([python, '-m', 'venv', str(workspace / 'python')], check=True)
        # Execute an immutable per-run copy: editing a shell script while bash
        # is reading it can otherwise change the next command mid-build.
        snapshot = args.out.resolve() / 'build_headless.snapshot.sh'
        snapshot.write_bytes((ROOT / 'scripts/build_headless.sh').read_bytes())
        report['build_script_sha256'] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        for name, argv in [
            ('python-install', [str(workspace / 'python/bin/python'), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-smoke.txt')]),
            ('headless-build', ['bash', str(snapshot), str(workspace), str(args.jobs)])
        ]:
            result = command(argv, REPO, args.out / (name + '.log'))
            report['commands'].append(result)
            if result['exit_code']:
                raise ValueError(name + ' failed; see log')
        report['status'] = 'BUILD_SUCCEEDED_SMOKE_NOT_RUN'
    except Exception as error:
        report.update(status='ENV_BLOCKED', error=str(error))
    finally:
        (args.out / 'setup.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        if report['status'] == 'ENV_BLOCKED':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
