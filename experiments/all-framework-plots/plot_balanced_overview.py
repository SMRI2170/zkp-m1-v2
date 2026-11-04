"""Readable, cross-scope overview of recorded balanced Pi results (no reruns)."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.data / 'summary.json').read_text())
    rows = [r for r in rows if r['status'] == 'completed']
    if not rows:
        raise SystemExit('No completed measurements')
    conditions = {(r['protocol'], r['host_class'], r['cpu_quota_percent'], r['threads'],
                   r['measured_samples'], r['warmup_samples']) for r in rows}
    if len(conditions) != 1:
        raise SystemExit('Protocol, host, CPU, threads or sample counts differ')
    rows.sort(key=lambda r: r['flow_ms']['mean'])
    args.out.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ticker import FuncFormatter
    if 'Hiragino Sans' in {f.name for f in font_manager.fontManager.ttflist}:
        plt.rcParams['font.family'] = 'Hiragino Sans'
    plt.rcParams.update({'font.size': 12, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.spines.left': False})
    names = {'circom-rapidsnark': 'Circom + RapidSnark *',
             'circom-snarkjs': 'Circom + snarkjs *',
             'gnark-groth16': 'gnark / Groth16', 'gnark-plonk': 'gnark / PLONK',
             'halo2-ipa': 'Halo2 / IPA', 'halo2-kzg': 'Halo2 / KZG',
             'arkworks': 'arkworks', 'spartan': 'Spartan', 'bulletproofs': 'Bulletproofs'}
    labels = [names.get(r['framework'], r['framework']) for r in rows]
    colors = ['#dc792f' if r['framework'].startswith('circom-') else '#3274a1' for r in rows]
    exports = []
    for r in rows:
        exports.append(dict(framework=r['framework'], n=r['measured_samples'],
                            flow_mean_ms=r['flow_ms']['mean'], flow_sd_ms=r['flow_ms']['sd'],
                            flow_median_ms=r['flow_ms']['median'],
                            memory_mean_MiB=r['whole_run_memory_mean_bytes'] / 2**20,
                            memory_peak_MiB=r['whole_run_kernel_peak_bytes'] / 2**20,
                            proof_mean_bytes=r['proof_bytes']['mean'],
                            flow_scope=r['flow_scope'], proof_encoding=r['proof_encoding']))
    with (args.out / 'comparison.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(exports[0])); writer.writeheader(); writer.writerows(exports)
    (args.out / 'comparison.json').write_text(json.dumps(exports, indent=2, ensure_ascii=False) + '\n')
    provenance = {name: hashlib.sha256((args.data / name).read_bytes()).hexdigest()
                  for name in ['summary.json', 'samples.jsonl', 'samples.csv']}
    (args.out / 'sources.json').write_text(json.dumps({'input': str(args.data), 'sha256': provenance,
                                                     'common_conditions': list(next(iter(conditions)))}, indent=2) + '\n')

    titles = ['処理時間：平均 ± 標準偏差', 'メモリ：全実行の平均と最大', '証明サイズ：保存形式の平均']
    def draw(ax, metric, show_labels):
        for i, (r, e, color) in enumerate(zip(rows, exports, colors)):
            ax.axhspan(i-.45, i+.45, color='#f1f4f7' if i % 2 == 0 else 'white', zorder=0)
            if metric == 0:
                v = e['flow_mean_ms'] / 1000
                ax.errorbar(v, i, xerr=e['flow_sd_ms']/1000, fmt='o', color=color,
                            capsize=4, markersize=7, linewidth=2, zorder=3)
                label = f'{v:.3f} 秒'
            elif metric == 1:
                v = e['memory_peak_MiB']
                ax.barh(i, v, height=.42, color=color, alpha=.85, zorder=2)
                ax.scatter(e['memory_mean_MiB'], i, color='white', edgecolor='#202c36', s=44, zorder=3)
                label = f"{e['memory_mean_MiB']:.1f} / {v:.1f}"
            else:
                v = e['proof_mean_bytes']
                ax.scatter(v, i, color=color, s=65, zorder=3)
                label = f'{v:,.0f} B'
            # Fixed label column avoids collisions with log ticks and neighbouring panels.
            ax.text(1.025, i, label, transform=ax.get_yaxis_transform(), va='center', fontsize=11)
        ax.set_ylim(len(rows)-.5, -.5)
        ax.set_yticks(range(len(rows)), labels if show_labels else ['']*len(rows))
        ax.tick_params(axis='y', length=0, pad=10)
        ax.grid(axis='x', alpha=.2, zorder=1)
        ax.set_title(titles[metric], loc='left', fontsize=14, pad=18, weight='bold')
        if metric == 0:
            ax.set_xscale('log'); ax.set_xlim(.08, 30)
            ax.set_xticks([.1, .3, 1, 3, 10, 30]); ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:g}'))
            ax.set_xlabel('秒（対数軸）／小さいほど短時間')
        elif metric == 1:
            ax.set_xlim(0, 120); ax.set_xticks([0, 30, 60, 90, 120])
            ax.set_xlabel('MiB ／白丸 = 平均、棒 = 最大\n右の数値：平均 / 最大')
        else:
            ax.set_xscale('log'); ax.set_xlim(80, 50000)
            ax.set_xticks([100, 1000, 10000]); ax.set_xticklabels(['100 B', '1 kB', '10 kB'])
            ax.set_xlabel('bytes（対数軸）／形式差を含む')

    footer = ('* オレンジ：WASM Witness生成 + prover起動 + 共通native verifier。青：各実装の記録済みprove/verify等。\n'
              '測定範囲・証明形式・暗号方式は同一ではありません。メモリは準備・ウォームアップ等も含む全実行の値。\n'
              '同一プロセス／鍵で7入力を各3回。標準偏差は観測値のばらつきであり、信頼区間ではありません。')
    fig, axes = plt.subplots(1, 3, figsize=(19, 9), gridspec_kw={'wspace': .50})
    for metric, ax in enumerate(axes): draw(ax, metric, metric == 0)
    fig.suptitle('Pi 4：9構成の統一比較', x=.16, ha='left', y=.97, fontsize=23, weight='bold')
    fig.text(.16, .91, '処理時間が短い順｜各 n=21（7入力 × 3回、別途ウォームアップ7回を除外）｜CPU 25%・1スレッド', fontsize=12)
    fig.text(.16, .025, footer, fontsize=11, linespacing=1.6)
    fig.subplots_adjust(left=.16, right=.92, top=.81, bottom=.22)
    for ext in ['png', 'svg']: fig.savefig(args.out / ('overview.' + ext), dpi=180)
    plt.close(fig)
    for metric, name in enumerate(['time', 'memory', 'proof-size']):
        fig, ax = plt.subplots(figsize=(11, 8))
        draw(ax, metric, True)
        fig.text(.26, .04, '各 n=21。* はCircom構成。詳細な測定範囲は統一比較図・説明を参照。', fontsize=10)
        fig.subplots_adjust(left=.26, right=.79, top=.9, bottom=.16)
        for ext in ['png', 'svg']: fig.savefig(args.out / (name + '.' + ext), dpi=180)
        plt.close(fig)


if __name__ == '__main__':
    main()
