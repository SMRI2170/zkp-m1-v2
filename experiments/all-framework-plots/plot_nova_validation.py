"""Export Nova validation figures from pinned, existing public synthetic logs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def load_lines(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    source = Path('week24/logs/pi-euclidean/euclidean-nova-v2')
    paths = [source / x for x in ['benchmark.jsonl', 'memory.jsonl', 'resource.json', 'memory-summary.json']]
    paths.append(Path('week23/logs/sonobe-current-security.json'))
    samples = [r for r in load_lines(paths[0]) if r['phase'] == 'sample']
    memory = load_lines(paths[1])
    resource = json.loads(paths[2].read_text())
    security = json.loads(paths[-1].read_text())
    assert len(samples) == 7 and all(r['verified'] for r in samples)
    assert resource['exit_code'] == 0
    a.out.mkdir(parents=True, exist_ok=False)
    export = []
    for r in security['runs']:
        canaries = [c for au in r['leak_audits'] if au['stage'] == r['stage']
                    for c in au['canaries'] if c['owner_stage'] == r['stage']]
        export.append({'hiding': r['hiding'], 'stage': r['stage'],
                       'tamper_tests': len(r['tamper_tests']),
                       'tamper_rejected': sum(t['rejected'] for t in r['tamper_tests']),
                       'own_canaries_detected': sum(bool(c['incoming_w_indices']) for c in canaries)})
    assert sum(r['tamper_rejected'] for r in export) == 132
    assert all(r['own_canaries_detected'] == 7 for r in export)
    step_rows = [{'step': i+1, 'case_id': r['case_id'], 'prove_ms': r['prove_ms'],
                  'verify_ms': r['verify_ms'], 'verified': r['verified']} for i, r in enumerate(samples)]
    for name, rows in [('pi-steps', step_rows), ('security', export)]:
        with (a.out / (name + '.csv')).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        (a.out / (name + '.json')).write_text(json.dumps(rows, indent=2) + '\n')
    (a.out / 'sources.json').write_text(json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 13})
    blue, gray, red = '#2F64A1', '#6B7A88', '#C72A2A'

    def save(fig, name, note):
        fig.text(.12, .025, note, fontsize=10)
        fig.subplots_adjust(left=.12, right=.97, bottom=.19, top=.86)
        for ext in ['png', 'svg']: fig.savefig(a.out / (name+'.'+ext), dpi=180)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(range(1, 8), [r['prove_ms']/1000 for r in samples], 'o-', color=blue, label='生成')
    ax.plot(range(1, 8), [r['verify_ms']/1000 for r in samples], 's-', color=gray, label='検証')
    ax.set(title='Nova / CycleFold：7stepの生成・検証時間', xlabel='step', ylabel='秒', xticks=range(1, 8), ylim=(0, 4))
    ax.grid(alpha=.2); ax.legend()
    save(fig, 'nova-step-times', 'Piの単一Prover raw IVC。7入力を各1回。独立反復の平均や、最終ZKの計測ではありません。')

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot([r['elapsed_s'] for r in memory], [r['cgroup_current_bytes']/2**20 for r in memory], color=blue, linewidth=1.5)
    peak = resource['cgroup_peak_bytes']/2**20
    ax.axhline(peak, linestyle='--', color=gray, label=f'カーネル最大 {peak:.1f} MiB')
    ax.set(title='Nova / CycleFold：実行全体のメモリ推移', xlabel='実行開始からの時間（秒）', ylabel='cgroupメモリ（MiB）', ylim=(0, 220))
    ax.grid(alpha=.2); ax.legend(loc='lower right')
    save(fig, 'nova-memory', '完走runのみ。準備・初期処理・負例検査を含む全unit。OOM・Swap使用0。')

    for field, name, title, ytitle, maximum in [
        ('tamper_rejected', 'nova-tamper', '固定Sonobe main：各段の改竄拒否数', '拒否数（各条件22件）', 25),
        ('own_canaries_detected', 'nova-canaries', '固定Sonobe main：生状態に残る識別用入力', '検出数（各段の当該入力7個）', 8),
    ]:
        fig, ax = plt.subplots(figsize=(11, 6))
        for h, offset, color in [(False, -.18, gray), (True, .18, blue if field == 'tamper_rejected' else red)]:
            selected = sorted([r for r in export if r['hiding'] == h], key=lambda r: r['stage'])
            bars = ax.bar([r['stage']+offset for r in selected], [r[field] for r in selected], width=.32, color=color, label=f'H={str(h).lower()}')
            ax.bar_label(bars, padding=4)
        ax.set(title=title, ylabel=ytitle, xticks=[1, 2, 3], xticklabels=['A', 'B', 'C'], ylim=(0, maximum))
        ax.grid(axis='y', alpha=.2); ax.legend(loc='upper right')
        note = ('22改竄 × 3段 × 両H = 132件を拒否。これだけで秘匿性を示すものではありません。'
                if field == 'tamper_rejected' else 'H=trueでも生状態には当該入力7個が残ります。暗号化・commitmentからの解読実験ではありません。')
        save(fig, name, note)


if __name__ == '__main__':
    main()
