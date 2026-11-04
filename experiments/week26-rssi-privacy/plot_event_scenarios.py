"""Japanese scientific figures for the synthetic event-association experiment."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

BLUE = '#173f73'
GREEN = '#00867c'
RED = '#b64c3c'
GRAY = '#bdc5cf'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('result', type=Path)
    root = p.parse_args().result
    s = json.loads((root / 'summary.json').read_text())
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((n for n in ['Hiragino Sans', 'Noto Sans CJK JP', 'IPAexGothic'] if n in available), None)
    if font is None:
        raise RuntimeError('Install a Japanese font before rendering these figures')
    plt.rcParams.update({'font.family': font, 'font.size': 11, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})

    def save(fig, name, caption):
        fig.text(.5, .014, caption, ha='center', fontsize=9, color='#444444')
        fig.tight_layout(rect=(0, .075, 1, .93))
        for ext in ['png', 'svg']:
            fig.savefig(root / f'{name}.{ext}')
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.8), sharey=True)
    schedules = [([list(range(5))] * 5, '全ノードが同じ送信を受信'),
                 ([[0, 1], [1], [1, 2, 3], [3], [2, 4]], '一部の送信だけ重複受信'),
                 ([[0], [1], [2], [3], [4]], '各送信を1ノードだけが受信')]
    for ax, (events, title) in zip(axes, schedules):
        for event, nodes in enumerate(events):
            color = GREEN if len(nodes) >= 2 else '#858d98'
            if len(nodes) >= 2:
                ax.plot([event, event], [min(nodes), max(nodes)], color=color, alpha=.45, linewidth=3)
            ax.scatter([event] * len(nodes), nodes, s=90, color=color, zorder=3)
            ax.text(event, 4.8, '検査' if len(nodes) >= 2 else '保留', ha='center', fontsize=9, color=color)
        ax.set(xticks=range(5), xticklabels=[f'e{i}' for i in range(5)], yticks=range(5),
               yticklabels=list('ABCDE'), xlabel='物理送信イベント（別の列＝別送信）',
               xlim=(-.5, 4.5), ylim=(5.2, -.6))
        ax.set_title(title, fontsize=12)
        ax.grid(axis='y', alpha=.15)
    axes[0].set_ylabel('受信ノード')
    fig.suptitle('送信ごとに電力を変更できても、同じ送信を受けたノード間では共通成分を除去', fontsize=14)
    save(fig, '01_observation_scenarios', '概念図：緑は整合性検査に使える組。検知成功・位置の正しさを保証する表示ではない。提出は後でもよい。')

    def case(mode, name, noise=2):
        return next(r for r in s['cases'] if r['mode'] == mode and r['case'] == name and r['noise_sd_db'] == noise)

    fig, ax = plt.subplots(1, 2, figsize=(13, 5.3))
    names = ['normal', 'power_plus16', 'power_random16', 'position30', 'position100', 'joint100']
    labels = ['正常', '電力だけ +16dB', '電力だけ送信ごとに変更', '位置だけ 30m改変', '位置だけ 100m改変', '位置100m ＋ 共通電力補償']
    values = [100 * case('full', n)['conditional_alarm_fraction'] for n in names]
    ax[0].barh(range(6), values, color=[GRAY, GREEN, GREEN, RED, RED, RED], height=.65)
    for i, v in enumerate(values):
        ax[0].text(v + 1, i, f'{v:.1f}%', va='center')
    ax[0].set(yticks=range(6), yticklabels=labels, xlim=(0, 100), xlabel='警報率（正常・電力のみでは誤警報率）')
    ax[0].invert_yaxis()
    ax[0].set_title('同一送信を5台受信：電力変更と位置改変', fontsize=12)
    modes = ['full', 'partial', 'single']
    rows = [case(m, 'position100') for m in modes]
    alarms = np.array([r['all_event_alarm_fraction'] for r in rows]) * 100
    abstain = np.array([r['abstain_fraction'] for r in rows]) * 100
    noalarm = 100 - alarms - abstain
    for v, left, color, label in [(alarms, 0, RED, '不整合の警報'),
             (noalarm, alarms, BLUE, '警報なし（正しさは未保証）'),
             (abstain, alarms + noalarm, GRAY, '判定保留')]:
        ax[1].barh(range(3), v, left=left, color=color, label=label, height=.55)
        for i, value in enumerate(v):
            if value >= 8:
                start = left if np.isscalar(left) else left[i]
                ax[1].text(start + value / 2, i, f'{value:.1f}%', ha='center', va='center',
                           color='white' if color in [BLUE, RED] else '#222222', fontsize=10)
    ax[1].set(yticks=range(3), yticklabels=['常に5台', '受信範囲が一部重複', '毎回1台のみ'],
               xlim=(0, 100), xlabel='全送信イベントに対する割合（%）')
    ax[1].invert_yaxis()
    ax[1].set_title('100m改変：検知と保留を同じ分母で表示', fontsize=12)
    ax[1].legend(loc='upper center', bbox_to_anchor=(.5, -.16), fontsize=9, ncol=1)
    save(fig, '02_alarm_and_abstention', '合成10 seed平均、雑音SD2dB。単独受信の条件付き検知率は未定義。受信範囲は幾何＋スキャン欠測の簡略モデル。')

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), sharey=True)
    for ax, sd in zip(axes, [2, 6]):
        for n, color in [(2, '#b35d27'), (3, GREEN), (5, BLUE)]:
            rows = [r for r in s['curves'] if r['noise_sd_db'] == sd and r['receivers'] == n]
            x = [r['shift_m'] for r in rows]
            y = [100 * r['conditional_alarm_fraction'] for r in rows]
            ax.plot(x, y, marker='o', color=color, label=f'{n}台')
            ax.fill_between(x, [100 * r['conditional_alarm_fraction_seed_min'] for r in rows],
                            [100 * r['conditional_alarm_fraction_seed_max'] for r in rows], color=color, alpha=.10)
        ax.set(title=f'独立リンク雑音 SD{sd}dB', xlabel='水平位置の改変量（m）', ylim=(0, 100))
        ax.legend()
        ax.grid(alpha=.15)
    axes[0].set_ylabel('警報率（0mでは正常誤警報率）（%）')
    fig.suptitle('同じ送信を複数台で受信しても、雑音・配置によって検知率は変わる', fontsize=14)
    save(fig, '03_displacement_and_noise', '全イベントを同じ台数で受信する合成条件。線＝10 seed平均、帯＝seed最小～最大（信頼区間ではない）。1台は全保留。')

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), gridspec_kw={'width_ratios': [1, 1, 1.1]})
    for ax, sd in zip(axes[:2], [2, 6]):
        for mode, color, label in [('stable', BLUE, '飛行中の電力一定'),
                   ('per_event_variable', RED, '送信ごとに電力変動 SD8dB')]:
            rows = [r for r in s['pairing'] if r['noise_sd_db'] == sd and r['power_mode'] == mode]
            ax.plot(range(len(rows)), [100 * r['conditional_alarm_fraction'] for r in rows], 'o-', color=color, label=label)
        ax.set(xticks=range(5), xticklabels=['0', '0.5', '1', '5', '15'],
               xlabel='組み合わせた観測の最大時刻差（秒）', ylim=(0, 100), title=f'別送信を混合：雑音SD{sd}dB')
        ax.legend(fontsize=8)
        ax.grid(alpha=.15)
    axes[0].set_ylabel('正常データへの誤警報率（%）')
    axes[2].axis('off')
    upload = [r for r in s['uploads'] if r['noise_sd_db'] == 2]
    table = axes[2].table(cellText=[[f'{r["upload_spread_s"]}秒', f'{100 * r["alarms"] / r["decidable_events"]:.2f}%',
                                   f'{r["decision_wait_s"]:.0f}秒'] for r in upload],
        colLabels=['提出の遅れ', '誤警報率', '判定待ち'], cellLoc='center', loc='center')
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 2)
    axes[2].set_title('同じ送信の提出だけ遅れる場合', fontsize=12)
    axes[2].text(.5, .12, '同一イベントを正しく対応付けた理想条件\n精度は同じ・判定は遅れる\n通信処理そのものの実測ではない',
                 ha='center', va='center', fontsize=10, transform=axes[2].transAxes)
    fig.suptitle('「受信した送信が違う」と「アップロードが遅い」は別の問題', fontsize=14)
    save(fig, '04_pairing_vs_upload_delay', '合成モデルの正常データのみ。0.5秒での電力変動量は仮定であり、実機の測定値や普遍的な時間上限ではない。')

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), gridspec_kw={'width_ratios': [1, .9, 1.2]})
    c = s['counterexamples']['circle']
    sites = np.asarray(c['observer_xyz']); theta = np.linspace(0, 2 * np.pi, 200)
    axes[0].plot(100 * np.cos(theta), 100 * np.sin(theta), '--', color=GRAY)
    axes[0].scatter(sites[:, 0], sites[:, 1], marker='s', s=80, color=BLUE)
    for label, pnt in zip('ABCD', sites):
        axes[0].annotate(label, pnt[:2], xytext=(5, 6), textcoords='offset points')
    axes[0].scatter([0], [0], marker='x', color=RED, s=80)
    axes[0].set(aspect='equal', xlim=(-135, 135), ylim=(-135, 135), xlabel='東西（m、架空座標）', ylabel='南北（m）', title='地上4台を半径100mの円周に配置')
    axes[1].scatter([0, 0], [20, 80], color=[RED, BLUE], s=100)
    axes[1].plot([0, 0], [20, 80], '--', color=GRAY)
    axes[1].text(.12, 20, '攻撃の世界\n実際は20m', va='center', color=RED)
    axes[1].text(.12, 80, '正常の世界\n実際は80m', va='center', color=BLUE)
    axes[1].set(xlim=(-.3, 1.5), ylim=(0, 110), xticks=[], ylabel='高度（m）', title='両方ともRID申告は高度80m')
    axes[2].plot(range(4), c['truthful_rssi_dbm'], 'o-', color=BLUE, markersize=9, label='正常：高度80m')
    axes[2].plot(range(4), c['attack_rssi_dbm'], 'x--', color=RED, markersize=10, label='偽装：高度20m＋電力補償')
    axes[2].set(xticks=range(4), xticklabels=list('ABCD'), ylim=(-91, -86), xlabel='受信ノード', ylabel='RSSI（dBm、合成）', title='全4台の観測値が一致')
    axes[2].legend(fontsize=9)
    axes[2].text(.5, .18, f'必要な基準電力変更：{c["attack_power_change_db"]:.2f}dB\nRSSI差：{c["max_rssi_difference_db"]:.2g}dB',
                 transform=axes[2].transAxes, ha='center', fontsize=10)
    fig.suptitle('できない例：複数ノードでも、配置によって位置と電力を区別できない', fontsize=14)
    save(fig, '05_geometry_counterexample', '雑音なしの数理反例。単一送信源・共通電力変更のみ。実RFの攻撃実証ではない。台数だけで保証は決まらない。')


if __name__ == '__main__':
    main()
