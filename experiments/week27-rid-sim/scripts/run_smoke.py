"""Run paired, real OMNeT++ smoke cases and audit actual vector output.

Missing dependencies produce NOT_RUN/ENV_BLOCKED, never placeholder events.
Raw synthetic truth/event ledgers remain private in ignored captures/.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import shutil
import signal
import time

from normalize import normalize, read_vectors, write_csv
from setup import ROOT, REPO


def env_command(workspace, argv):
    return ['bash', '-c', 'set -e; w="$1"; shift; source "$w/omnetpp-6.2.0/setenv" -q; '
            'source "$w/inet4.5/setenv" -q; exec "$@"', 'rid-smoke', str(workspace), *map(str, argv)]


def run_logged(workspace, argv, cwd, log, timeout, watch_dir=None, max_bytes=None, min_free_bytes=None):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason=None; clock=time.monotonic()
    with log.open('w') as stream:
        process=subprocess.Popen(env_command(workspace,argv),cwd=cwd,stdout=stream,
                                 stderr=subprocess.STDOUT,start_new_session=True)
        while process.poll() is None:
            if time.monotonic()-clock>timeout:reason='timeout'
            if watch_dir is not None:
                size=sum(p.stat().st_size for p in Path(watch_dir).glob('*') if p.is_file())
                if max_bytes is not None and size>max_bytes:reason='output_size_budget'
                if min_free_bytes is not None and shutil.disk_usage(watch_dir).free<min_free_bytes:reason='disk_headroom_budget'
            if reason:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                break
            try:process.wait(timeout=.2)
            except subprocess.TimeoutExpired:pass
    code=124 if reason=='timeout' else process.returncode
    return dict(started_utc=started, argv=list(map(str, argv)), exit_code=code,
                stop_reason=reason,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())


def assert_case(case, rows, tx, summary):
    if not summary['rx_delivered'] or not summary['rss_samples'] or not summary['gcs_events']:
        raise ValueError('No RX/RSSI/GCS evidence: communication smoke failed')
    if any(t['true_tx_xyz'] is None or t['claimed_xyz'] is None or t['tx_power_dbm_truth_only'] is None for t in tx):
        raise ValueError('Incomplete TX truth ledger')
    for t in tx:
        changed = t['true_tx_xyz'] != t['claimed_xyz']
        if changed != (case == 'StaticSpoof') or t['is_spoofed'] != int(case == 'StaticSpoof'):
            raise ValueError('Claim/attack label does not match requested smoke case')
    if summary['receiver_opportunities'] != summary['rx_delivered'] + summary['not_observed']:
        raise ValueError('TX/receiver denominator accounting failed')


def paired_audit(cases):
    result, received = {}, {}
    for case, rows in cases.items():
        offsets = [math.dist(r['true_tx_xyz'], r['claimed_xyz']) for r in rows]
        received[case] = {(r['tx_time'], r['rx_node_id']): r['rssi_dbm'] for r in rows if r['rssi_dbm'] is not None}
        rss = list(received[case].values())
        result[case] = dict(claim_displacement_min_m=min(offsets), claim_displacement_max_m=max(offsets),
                            rssi_min_dbm=min(rss), rssi_max_dbm=max(rss),
                            received_serial_values=sorted({r['serial'] for r in rows if r['serial'] is not None}),
                            claimed_timestamp_distinct=len({r['claimed_timestamp'] for r in rows if r['claimed_timestamp'] is not None}))
    shared = received['Normal'].keys() & received['StaticSpoof'].keys()
    result['paired_received_opportunities'] = len(shared)
    result['paired_rssi_max_abs_diff_db'] = max((abs(received['Normal'][k] - received['StaticSpoof'][k]) for k in shared), default=None)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, default=REPO / '.cache/issue70')
    p.add_argument('--raw-dir', type=Path, required=True)
    p.add_argument('--summary-dir', type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    raw = args.raw_dir.resolve()
    if not raw.is_relative_to((REPO / 'captures').resolve()) or raw == (REPO / 'captures').resolve():
        p.error('Use a dedicated ignored captures/ directory')
    if raw.exists() or args.summary_dir.exists():
        p.error('Choose new output directories; preserving prior execution evidence')
    raw.mkdir(parents=True, mode=0o700)
    args.summary_dir.mkdir(parents=True)
    workspace = args.workspace.resolve()
    lock = json.loads((ROOT / 'upstream.lock.json').read_text())
    config = json.loads((ROOT / 'config/smoke.json').read_text())
    result = dict(dataset_source='simulation', scope='PR1 communication/spoofer smoke, no detector',
                  seed=config['seed'], upstream_sha=lock['uli_net_sim']['sha'],
                  observer_regime=config['observer_regime'], status='ENV_BLOCKED',
                  cases=[dict(case=c, status='NOT_RUN') for c in config['cases']],
                  limitations=['No FPR/TPR estimation or real Remote ID RF measurements.',
                               'Management enqueue is not confirmed PHY TX.',
                               'GCS exposes first packet ID, not all per-report packet IDs.',
                               'Multiple-site smoke is a comparison condition, not the asynchronous research solution.'])
    try:
        upstream = workspace / 'uli-net-sim'
        sha = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        if sha != lock['uli_net_sim']['sha']:
            raise ValueError('Upstream SHA mismatch')
        if subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain'], text=True).strip():
            raise ValueError('Upstream local edits detected')
        binary = workspace / 'project-build/out/clang-release/rid_smoke'
        if not binary.is_file():
            raise ValueError('Simulator binary missing; build PR1 environment first')
        result['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        result['python_version'] = sys.version.split()[0]
        ini = raw / 'smoke.ini'
        ini.write_text((ROOT / 'config/smoke.ini').read_text().replace('@CALLBACK_PATH@', str(ROOT / 'scripts')))
        exclusions = ';'.join((workspace / 'inet4.5/.nedexclusions').read_text().splitlines())
        paired_truth, case_rows = [], {}
        for case, case_result in zip(config['cases'], result['cases']):
            case_dir = raw / case
            case_dir.mkdir(mode=0o700)
            argv = [binary, '-u', 'Cmdenv', '-n', f'{upstream}/src:{workspace}/inet4.5/src',
                    '-x', exclusions, '-f', ini, '-c', case, '-r', '0',
                    f'--seed-set={config["seed"]}', '--simtime-resolution=ps',
                    f'--output-vector-file={case_dir}/run.vec',
                    f'--output-scalar-file={case_dir}/run.sca']
            receipt = run_logged(workspace, argv, upstream, case_dir / 'simulation.log', 120)
            (case_dir / 'execution.json').write_text(json.dumps(receipt, indent=2) + '\n')
            case_result.update(status='SIMULATION_FAILED', execution_exit_code=receipt['exit_code'],
                               simulation_log_sha256=receipt['log_sha256'])
            if receipt['exit_code']:
                raise ValueError(case + ' simulation failed; inspect private simulation.log')
            case_result['status'] = 'SIMULATION_COMPLETED_AUDIT_PENDING'
            # Preserve the upstream converter output too, but do not trust its
            # row-index alignment / synthesized TX serial/timestamp for audit.
            conversion = run_logged(workspace, [workspace / 'python/bin/python',
                upstream / 'datagen/vec2parquet.py', case_dir / 'run.vec', '-o', case_dir / 'upstream.parquet'],
                upstream, case_dir / 'conversion.log', 60)
            case_result['upstream_conversion_exit_code'] = conversion['exit_code']
            if conversion['exit_code']:
                case_result['status'] = 'CONVERSION_FAILED'
                raise ValueError(case + ' upstream Parquet conversion failed')
            rows, tx, gcs, summary = normalize(read_vectors(case_dir / 'run.vec'), case, config)
            assert_case(case, rows, tx, summary)
            write_csv(case_dir / 'observations.csv', rows)
            write_csv(case_dir / 'tx-ledger.csv', tx)
            write_csv(case_dir / 'gcs.csv', gcs)
            import pyarrow as pa
            import pyarrow.parquet as pq
            pq.write_table(pa.Table.from_pylist(rows), case_dir / 'observations.parquet')
            case_result.update(summary, status='SMOKE_PASSED',
                               vector_sha256=hashlib.sha256((case_dir / 'run.vec').read_bytes()).hexdigest())
            paired_truth.append([(t['tx_time'], t['true_tx_xyz'], t['tx_power_dbm_truth_only']) for t in tx])
            case_rows[case] = rows
        if paired_truth[0] != paired_truth[1]:
            raise ValueError('Paired TX schedules, true trajectories or powers differ')
        result.update(status='PR1_SMOKE_PASSED', paired_truth_schedule_power_equal=True,
                      next_stage='PR2_NOT_RUN')
        (args.summary_dir / 'paired-audit.json').write_text(json.dumps(paired_audit(case_rows), indent=2) + '\n')
    except Exception as error:
        result['error'] = str(error)
        if any(c['status'] != 'NOT_RUN' for c in result['cases']):
            result['status'] = 'PR1_FAILED'
    finally:
        # Publish aggregate counts only, never truth/observation rows.
        (args.summary_dir / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        write_csv(args.summary_dir / 'case-summary.csv', result['cases'])
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PR1_SMOKE_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
